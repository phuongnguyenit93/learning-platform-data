# Managing Versions via the Spring Boot BOM and Controlling Dependency Overrides

> **Context:** Spring Security fundamentals · **Versions and Next Steps** group · Spring Boot 3.x, Java 17+, Maven, and Gradle. This lesson explains the **BOM (Bill of Materials)**, how Spring Boot manages the versions of Spring Security and related libraries, how to override deliberately, how to inspect the actual resolved version, and the update workflow to avoid dependency drift. The examples use **Spring Boot 3.5.16** as a snapshot verified against official documentation; this number is only for reproducing the lesson, not a recommendation to stay on it permanently in production.

## 1. The Problem: Why Not Pick a Version for Each Library Yourself?

In Spring Boot, we usually write in Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

or in Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
```

There is no `<version>` or `:version` because the project usually already uses **Spring Boot dependency management**. Spring Boot publishes a set of versions tested together: Spring Security, Spring Framework, Jackson, logging, the servlet container, testing libraries, and many other components.

If a learner manually adds:

```groovy
// Dangerous example for identification, do not use in production:
implementation 'org.springframework.security:spring-security-web:6.4.5'
implementation 'org.springframework.security:spring-security-config:6.5.11'
```

then the Security modules group can end up with mismatched versions. How Gradle actually resolves them may differ from the numbers written directly, and if the final classpath is incompatible, it can cause `NoSuchMethodError`, `NoClassDefFoundError`, unexpected filter behavior, or missed security patches. Pinning every module manually means the project takes on the compatibility burden that the BOM was designed to alleviate.

### Learning Outcomes

After this lesson, you should be able to answer: what a BOM is and how it differs from a starter; how a Maven parent differs from a Maven imported BOM; how Gradle's `io.spring.dependency-management` differs from native `platform(...)`; how to override; why you must inspect the **resolved graph**; when to upgrade a Boot patch rather than patching only one Spring Security module; and how to prevent dependency drift in CI/CD.

## 2. BOM, Starter, Plugin, and Resolved Graph

### 2.1. BOM (Bill of Materials)

Spring Boot provides `org.springframework.boot:spring-boot-dependencies`. This is a POM managing the `groupId:artifactId:version` coordinates of a curated set of libraries compatible with a given Spring Boot release.

```text
Project selects Spring Boot 3.5.16
           |
           v
spring-boot-dependencies:3.5.16
           |
           +-- Spring Security core/web/config/test -> 6.5.11
           +-- Spring Framework modules             -> curated versions
           +-- Jackson, Logback, Tomcat, ...         -> curated versions
           |
           v
Build tool resolves graph from declared project dependencies
           |
           v
Actual compile / runtime / test classpaths
```

According to the managed coordinates table for Spring Boot 3.5.16, the modules `spring-security-core`, `spring-security-config`, `spring-security-web`, and `spring-security-test` share version **6.5.11**. This information is **tied to a specific Boot release**; when changing Boot versions, read the new table and re-run the dependency tree.

**A BOM does not add libraries by itself.** It manages versions for artifacts already in the graph; it does not automatically add Spring Security to the classpath.

### 2.2. Starter

`spring-boot-starter-security` is a starter dependency that pulls the necessary modules onto the classpath via transitive dependencies. Starters and BOMs have different roles:

- Starter: **which libraries are needed**?
- BOM: **which versions should be used for managed libraries**?
- Build resolver: after all constraints and overrides, **which version is actually selected**?

A version in the BOM is not always the runtime version: an explicit direct version, another BOM, constraints, a lockfile, conflict resolution, or a forced version can change the result.

### 2.3. Dependency Management vs. Plugin Management

| Component | Function | Example |
| --- | --- | --- |
| Maven `<dependencies>` | Adds artifacts to the graph | `spring-boot-starter-security` |
| Maven `<dependencyManagement>` | Controls dependency version metadata | `spring-boot-dependencies` import |
| Maven `<pluginManagement>` | Controls build plugins | `maven-compiler-plugin` |
| Gradle `plugins` | Build tool plugin versions | `org.springframework.boot` plugin |
| Gradle `platform(...)` | Native constraints from a BOM | `spring-boot-dependencies` |
| Gradle dependency-management plugin | Maven-style dependency management | `io.spring.dependency-management` |

Do not confuse `spring-boot-maven-plugin` with `spring-boot-dependencies`. Importing a BOM does not bring in all the compiler/repackage configurations of `spring-boot-starter-parent`.

## 3. Principles for Choosing Spring Boot and Spring Security Versions

A Boot release is designed and tested against a specific set of versions. Safe practice is typically:

1. **Choose a supported Spring Boot release** matching your Java and framework stack.
2. Use the BOM accompanying that release to manage dependencies.
3. Do not declare versions for starters/modules already covered by the BOM, unless there is a reviewed reason to override.
4. Track security patches; when a new Boot patch is released, consider upgrading Boot/BOM first.
5. Only override directly when genuinely necessary and after verifying compatibility.
6. Then verify via the **resolved graph and integration tests**, not just by reading the POM/Gradle file.

**Warning:** Spring Security major 7.x is not a “patch” to drop into Boot 3.5.x in place of Security 6.5.x. Major lines can require a newer Spring Framework and introduce breaking API changes. Upgrading Security/Framework/Boot majors requires checking the compatibility matrix and migration guide, rather than mixing versions merely because a version number is higher.

Version numbers in the examples are a learning snapshot; when revisiting this lesson later, consult the current `Managed Dependency Coordinates` table and support policy.

## 4. Maven Option A: Inheriting spring-boot-starter-parent

A **complete** `pom.xml` for a Java 17 lab:

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bom-security-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

**Why does this work without versions on dependencies?** The parent inherits the BOM, which manages the starters and `spring-security-test`. The parent also brings compiler defaults, resource filtering, and plugin management. Java 17 is declared in properties. There is no need to pin separate versions for Security core/web/config/test.

`<relativePath/>` tells Maven not to search for a parent POM at `../pom.xml`, avoiding accidental matches with a corporate/local parent file if one happens to sit nearby.

### Inspecting Parent and Graph

```bash
# When the project has Maven Wrapper:
./mvnw test
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dscope=test
./mvnw help:evaluate -Dexpression=project.parent.version -q -DforceStdout
```

The `project.parent.version` value from the illustrative POM is `3.5.16`. Exact `dependency:tree` details depend on the actual graph and plugin version; inspect **all resolved Security modules**, rather than expecting the printed tree to follow a rigid exact order.

## 5. Maven Option B: Importing the BOM When Using a Corporate Parent

Maven allows only **one direct parent**. If an application already inherits a corporate parent, it cannot simultaneously inherit `spring-boot-starter-parent` as a second parent. In that case, you can **import the Spring Boot BOM**:

```xml
<!-- Fragment of pom.xml with another parent, not a complete POM -->
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.5.16</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
```

A BOM import manages dependency versions; it **does not bring along all build plugin defaults** from the Boot parent. If the corporate parent does not manage the appropriate compiler, plugin, and repackage setup, you must configure them explicitly. Example fragment:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
            <executions>
                <execution>
                    <goals><goal>repackage</goal></goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

This is an example of **additional build configuration**; do not paste it into a corporate parent setup if that parent already defines its own rules. `dependencyManagement` and `pluginManagement` are two separate systems.

## 6. Maven Overrides: Parent Property vs. Imported BOM

### 6.1. When Inheriting the Boot Parent

Spring Boot uses properties for managed versions. For example:

```xml
<!-- In <properties> of a POM with a Spring Boot parent -->
<properties>
    <java.version>17</java.version>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
```

With Boot 3.5.16, `6.5.11` is already the BOM-managed version; this snippet **illustrates the property mechanism**, not an upgrade. If you must patch to another version, replace it with an **actual upstream-released version** whose compatibility has been verified, then inspect `effective-pom` and `dependency:tree`.

Boot also has a `spring-framework.version` property. Do not pin Spring Framework manually just because a newer version exists: Spring Security and Boot depend on a compatible Framework baseline.

### 6.2. When Only Importing the BOM

If you **do not inherit the Boot parent** and only import `spring-boot-dependencies`, setting `spring-security.version` in the project **does not modify the properties inside the imported BOM the way parent inheritance does**. According to the Spring Boot Maven docs, to override, you must add an entry directly in `<dependencyManagement>` ahead of the BOM import:

```xml
<!-- Syntax illustration example; 6.5.11 matches the BOM version, not an upgrade -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-web</artifactId>
            <version>6.5.11</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

**Warning:** overriding `spring-security-web` alone does not guarantee that `spring-security-config`, `core`, `test`, and OAuth2 modules are also updated. When you need to override the entire Security family, consider the Spring Security BOM (or a controlled family of entries) and check precedence across BOMs. **The preferred approach is usually upgrading the Boot patch to receive an integrated, tested set**.

### 6.3. Direct Dependency Version Is Not a “Managed Version”

If you write `<version>6.4.5</version>` directly on `spring-security-web` inside `<dependencies>`, that is a specific request for this dependency. It may diverge from other `dependencyManagement` rules or transitive modules. Do not rely on reading a single line in the POM to assert the runtime version; use the Maven dependency tree.

## 7. Gradle Option A: io.spring.dependency-management

The Spring Boot Gradle plugin detects when `io.spring.dependency-management` is applied and automatically imports the BOM matching the Boot plugin version.

`settings.gradle`:

```groovy
rootProject.name = 'bom-security-demo'
```

**Complete `build.gradle` — Option A**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This snippet uses the **Spring Boot plugin** version to determine which BOM is imported. You do not need to specify separate versions for the starters or `spring-security-test`.

If you need to override via a BOM property:

```groovy
// Insert into Option A build.gradle after review.
// 6.5.11 is the version selected by default by BOM 3.5.16.
ext['spring-security.version'] = '6.5.11'
```

The property value can be replaced with an appropriate upstream patch, provided you run `dependencyInsight` and regression tests. For projects **publishing a Maven POM**, property overrides in the Gradle dependency-management plugin have limitations regarding the published POM; consult the plugin documentation and consider overriding via dependency-management entries so published metadata reflects the choice accurately.

**Do not arbitrarily combine this with Option B's `platform(...)`** without clearly identifying the management source and precedence.

## 8. Gradle Option B: Native platform(...)

Gradle supports importing a Maven BOM using `platform(...)` without the dependency-management plugin.

`build.gradle` **replacing Option A completely**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`SpringBootPlugin.BOM_COORDINATES` points to the BOM matching the declared Boot plugin version. `platform` adds **version constraints** to the configuration. Depending on the graph, another version requirement can cause the resolved version to **differ from the version in the BOM**; therefore `dependencyInsight` is necessary. Importing a BOM only affects the declared configurations and configurations that inherit from them appropriately; the example puts it in both `implementation` and `testImplementation` to make the intent explicit.

### platform vs. enforcedPlatform

| Mechanism | Meaning | Trade-off |
| --- | --- | --- |
| `platform(...)` | BOM versions act as constraints/recommendations; the resolver can pick a different version | Generally more flexible; inspect the selected version |
| `enforcedPlatform(...)` | Strongly forces BOM versions via strict constraints | Can cause conflicts or impose limits on consumers |
| `strictly(...)` on dependency | Requests a strict version | Resolution may fail if constraints are incompatible |
| `resolutionStrategy.force(...)` | Forces a chosen version | Easily masks incompatibilities; requires special review |

**Do not use enforcedPlatform to “patch security” by forcing an older version.** If a library requires a newer patch, forcing an older BOM can make the runtime incompatible or leave a CVE unpatched.

### Native platform Does Not Accept Plugin A Style Property Overrides

In Gradle native `platform`, `ext['spring-security.version'] = '...'` does not modify the internal properties of the Spring Boot BOM as it does with `io.spring.dependency-management`. To override, you must use a valid Gradle mechanism: a version constraint, an explicit version, a resolution strategy, or another deliberate platform/BOM. Inspect the resolved graph to confirm.

## 9. Override Sources and Precedence

| Context | Where overrides arise | What to inspect |
| --- | --- | --- |
| Maven inherit parent | `spring-security.version`, `spring-framework.version` | Effective POM |
| Maven import BOM | Separate entry in `dependencyManagement` | Local POM vs. imported BOM |
| Maven direct dependency | `<dependency><version>...` | Direct version vs. management |
| Maven multiple BOMs | Order of imports and direct entries | For conflicting BOMs, Maven follows Maven import rules |
| Gradle dependency-management plugin | `ext['...']`, DSL imports/dependencies | A **later** BOM import can override an earlier BOM |
| Gradle native platform | Constraints, explicit versions | Resolver picks across the graph, not simple “last wins” |
| Gradle force/strict | `enforcedPlatform`, `strictly`, `force` | May over-override or lock versions too rigidly |
| Gradle version catalog | `libs.versions.toml` aliases | Catalog does not automatically constrain the whole graph |
| Lockfiles | Locked resolved versions | Updating a BOM may not change runtime until locks are refreshed |

### 9.1. Maven and Gradle Plugin Have Different BOM Ordering Rules

In Maven, an entry declared directly in the project's `dependencyManagement` takes precedence over imported management. When **two imported BOMs** manage the same coordinates, Maven uses import order per its own rules (the BOM appearing first usually wins in a conflict).

In Gradle's **io.spring.dependency-management plugin**, BOMs are processed in import order and dependency management from the **last** BOM can win for the same module. **Gradle native platform** uses version constraints/conflict resolution, so you cannot assume “last BOM wins”.

This is why you must not copy the order of `mavenBom(...)` from a Gradle project into Maven and assume identical behavior.

### 9.2. Spring Security BOM and Spring Framework BOM

When using Spring Boot, prefer letting the Boot BOM stay in control. Only import `spring-security-bom` separately if you have a **clear reason**, a verified compatible version, and understand precedence. A Boot 3.5.x + Security 7.x combination is not an automatic patch; Security 7.x may require Spring Framework 7.x.

When you need to override a Security 6.5.x patch, review all related modules (core/config/web/test/oauth2) and foundational libraries, not just `spring-security-web`. The right time to remove the override is when a new Boot release manages the fix.

## 10. Reading Maven Dependency Tree and Effective POM

Start with:

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dscope=test
./mvnw help:evaluate -Dexpression=spring-security.version -q -DforceStdout
```

Read them to find out:

- Has `effective-pom.xml` imported the right BOM and parent?
- Are there any property overrides or direct `dependencyManagement` entries?
- Is there an additional corporate parent or Maven profile altering versions?
- What are the final versions of `spring-security-core`, `config`, `web`, and `test`?
- Have `spring-core`, `spring-web`, Jackson, or Logback drifted from the curated set?
- Are plugin/compiler versions different between laptop and CI?

**Note:** `help:evaluate` printing a property value does not prove the classpath uses that version. When only importing a BOM, a project property may not affect the imported BOM the way parent inheritance does. `dependency:tree` is what shows actual resolution.

Condensed **illustrative** tree example, not verbatim real output:

```text
spring-boot-starter-security:3.5.16
  +-- spring-security-config:6.5.11
  +-- spring-security-web:6.5.11
  +-- spring-security-core:6.5.11
spring-security-test:6.5.11 [test]
```

The goal is comparing versions across the **entire family**, not relying on the exact tree order or indentation of a specific Maven plugin version.

### Maven Nearest Definition Rule

In Maven, transitive conflicts typically use “nearest definition”; at equal depth, declaration order can apply. `dependencyManagement` adds version management rules, and directly declared versions have their own precedence. Do not extrapolate Maven mediation rules to Gradle native resolution, as the two tools use different mechanisms.

## 11. Reading Gradle Dependencies and dependencyInsight

```bash
# View runtime graph:
./gradlew dependencies --configuration runtimeClasspath

# Investigate a specific module:
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

# Separate test version:
./gradlew dependencyInsight \
  --dependency spring-security-test \
  --configuration testRuntimeClasspath

# Check foundational libraries:
./gradlew dependencyInsight \
  --dependency spring-core \
  --configuration runtimeClasspath
```

`dependencyInsight` reveals the **requested version**, **selected version**, selection reason (constraint/conflict/force/strict depending on Gradle version), and the dependency path pulling the module in. If `build.gradle` requests `6.4.x` while the final graph uses `6.5.x`, do not report “downgraded” just from reading the declaration; inspect the selected version.

`runtimeClasspath` and `testRuntimeClasspath` can differ. A `spring-security-test` with a mismatched major/minor version can break tests or mask compatibility issues. Do not treat passing tests with a mocked principal as complete proof of runtime JWT/session authentication.

## 12. Java 17 Spring Boot Demo Compatible with the Build Configurations Above

Use one source set with either Maven or **one** chosen Gradle variant:

```text
bom-security-demo/
  pom.xml                 # When using Maven
  build.gradle            # When using Gradle, choose Option A or B
  settings.gradle
  src/main/java/com/example/bomdemo/
      BomDemoApplication.java
      SecurityConfig.java
      PingController.java
  src/test/java/com/example/bomdemo/
      SecuritySmokeTest.java
```

### `BomDemoApplication.java`

```java
package com.example.bomdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BomDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BomDemoApplication.class, args);
    }
}
```

### `SecurityConfig.java`

```java
package com.example.bomdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

### `PingController.java`

```java
package com.example.bomdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

### `SecuritySmokeTest.java`

```java
package com.example.bomdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecuritySmokeTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsRejected() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetsPong() throws Exception {
        mvc.perform(get("/api/ping")
                .with(user("learner").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }
}
```

Run with Maven wrapper:

```bash
./mvnw clean test
./mvnw package
./mvnw spring-boot:run
```

Or Gradle wrapper:

```bash
./gradlew clean test
./gradlew bootJar
./gradlew bootRun
```

If the project does not have a wrapper yet, you need a compatible Maven/Gradle installation or to generate the wrapper per project policy. Java source code needs the classpath provided by the build tool; you cannot run `javac` on individual files standalone without Spring dependencies.

**Test result:** anonymous GET `/api/ping` receives 401 from the HTTP Basic entry point; the request with `with(user(...))` returns 200 and exact body `pong`. This is an HTTP body, **not stdout from `java`**. The test uses a mock principal to verify the Spring Security filter chain; it does not test a real user/password database. For a local app without a custom `UserDetailsService`, Boot may generate a default user/password; do not use that default user mechanism as production authentication.

## 13. When a CVE Is Found: Upgrade Boot First or Override?

Recommended workflow:

1. Verify the affected **artifact/group/version**, advisory, and exploit conditions; scanners are not always right about runtime applicability.
2. Identify the transitive path using `dependency:tree` or `dependencyInsight`.
3. Check whether a **supported Boot patch release** already upgrades this artifact. If so, prefer upgrading the parent/plugin/BOM.
4. If Boot does not yet have a fix and the risk level demands urgent action, choose a **targeted override** with compatibility review and limited scope.
5. For Spring Security, review the **same-family module set**, not just a single artifact; for Framework, review the baseline supported by Boot.
6. Run compile, unit/integration tests, MockMvc filter chain tests, authentication/authorization, CSRF, sessions, and OAuth2/JWT if the application uses them.
7. Verify selected dependencies and the **artifact/JAR/container image**, generate an SBOM, and re-scan for actual CVEs.
8. Record owner, reason, expiration date, and rollback path.
9. Once a new Boot BOM integrates the patch, **remove the temporary override**, and re-verify the graph and tests.

Example record:

```text
Dependency: org.springframework.security:spring-security-web
Baseline: application Spring Boot BOM
Finding: official advisory, description of applicability conditions
Decision: upgrade Boot patch or reviewed family override
Evidence: dependency tree + MockMvc + runtime test + SBOM
Owner/Expiry: approver, date when override must be removed
```

Do not claim “Security 7.x is always better than Security 6.5.x” if the project's Boot/Framework is not ready for a major upgrade. And do not leave an override in place indefinitely once the Boot BOM manages the same fixed version.

## 14. Multiple BOMs, Multi-Module Projects, and Lockfiles

In real projects, besides the Boot BOM there may be Spring Cloud, Testcontainers, Jackson, Netty, external SDKs, or a corporate BOM. One module can be **managed by multiple BOMs simultaneously**. Always check the compatibility matrix of other BOMs (especially the Spring Cloud release train vs. Boot) and the build tool's resolution rules.

### Maven Multi-Module

- The parent manages `dependencyManagement`; children must **inherit the parent**, not merely be listed in `<modules>`.
- Children declare the dependencies they use, avoiding version pins that conflict with the parent.
- An aggregator with `<modules>` does not automatically make a child inherit the BOM if the child does not declare `<parent>`.
- Do not let module A use Security 6.4 and module B use 6.5 and package them together without review.

### Gradle Multi-Project

- You can use convention plugins or version catalogs to share plugin versions and dependency declarations.
- `libs.versions.toml` is a catalog of requested aliases/versions; it **does not replace resolving BOM constraints**.
- Each subproject needs the proper platform/dependency-management applied to the configurations it uses.
- Run `dependencyInsight` for `:api` and `:security-config` separately if needed, not only on the root.

### Dependency Locking

Gradle dependency locking records the selected versions for locked configurations, which is useful for reproducible releases but **does not automatically pull in patches**.

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

With locking enabled:

```bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
./gradlew dependencies --configuration testRuntimeClasspath --write-locks
```

Commit/review lockfiles according to policy; when upgrading a BOM, update the locks and verify they do not retain vulnerable versions. `platform` is not a lockfile; `enforcedPlatform` also does not replace supply-chain verification.

## 15. Supply Chain, Reproducibility, and Release Gates

A BOM keeps dependencies aligned, but does not by itself guarantee:

- Identical Maven/Gradle wrapper versions on laptops and in CI.
- The right JDK/toolchain release; Boot 3.5.16 requires Java 17+ and a supported Gradle/Maven version.
- Trusted repositories; restrict dynamic versions, snapshots/milestones unless governed by a process.
- Hash/signature/dependency verification to catch artifacts from untrusted sources.
- SBOM/SCA scanning on the actual artifact and runtime classpath.
- Correct data permissions, authentication, and CSRF code.
- Gradle lockfiles synchronized with the BOM.
- No other imported BOM overriding versions.
- No `resolutionStrategy.force(...)` from a corporate plugin altering the selected version unexpectedly.

### Illustrative CI Pipeline

```text
Build tool wrapper + approved JDK
    |
    v
Resolve managed dependencies
    |
    v
Check effective POM / dependencyInsight / locking
    |
    v
Compile + unit + Spring Security integration tests
    |
    v
Package JAR/container + generate SBOM
    |
    v
Dependency vulnerability/licensing checks
    |
    v
Staging smoke tests + approval
    |
    v
Deploy the exact tested artifact digest
```

Do not rebuild a production artifact from a modified POM/Gradle graph after staging passes. The BOM version in Git is part of release provenance, but you must also record the resolved dependency graph and artifact digest.

## 16. Diagnosing Common Errors

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Maven reports missing dependency version | Not inheriting Boot parent, missing BOM import, or child lacks parent | `help:effective-pom` |
| Maven version property has no effect | Importing BOM instead of inheriting parent | Check dependencyManagement/override entries |
| Gradle ext property does not change classpath | Using native platform instead of dependency-management plugin | `dependencyInsight` |
| Build compiles cleanly but runtime `NoSuchMethodError` | Runtime JARs mismatched, binary-incompatible API | Inspect runtimeClasspath and tree |
| `spring-security-test` API error in tests | Test module out of sync with core/web/config | Inspect testRuntimeClasspath |
| Upgraded Boot plugin but libraries stay old | Gradle lockfile, explicit version, another BOM, or force | `dependencyInsight` and locks |
| Maven and Gradle resolve different versions | Different management semantics, plugins, or profiles/repositories | Compare resolved graphs |
| CVE remains in image after fix PR | Stale build artifact, un-upgraded transitive dependency | SBOM and artifact digest |
| Spring Security major update breaks startup | Incompatible Boot/Framework baseline | Migration guide, revert and retest |
| A path filter behaves differently after bump | Security fix changed rules/ordering, unsuitable matcher config | Full-chain MockMvc + live HTTP tests |

**Distinguishing build errors from runtime errors:** compilation catches some API mismatches; linkage errors like `NoSuchMethodError` only appear when the JVM executes the affected code path. A passing unit test with `@WithMockUser` does not prove the full runtime authentication pipeline works with an IdP/JWT.

## 17. Version Management Mistakes to Avoid

1. Pinning separate versions for every Spring Boot starter despite having a BOM.
2. Assuming importing a BOM automatically adds Spring Security to the classpath.
3. Assuming Maven `dependencyManagement` also manages Maven plugin versions.
4. Confusing property overrides in a **Maven parent** with a **Maven imported BOM**.
5. Using `ext['spring-security.version']` with **native Gradle platform** and assuming the BOM changes.
6. Mixing multiple Gradle management approaches without knowing which one wins.
7. Importing a Spring Security BOM from a different major than the Boot baseline.
8. Overriding only `spring-security-web` without checking `core`/`config`/`test`.
9. Ignoring Maven BOM import order or Gradle plugin BOM import order.
10. Trusting numbers declared in the build file instead of resolved versions.
11. Neglecting `testRuntimeClasspath`, Gradle lockfiles, or corporate plugins.
12. Broadly forcing `enforcedPlatform`/`force` just to silence warnings.
13. Upgrading majors solely because a “newer version exists” without reading the migration guide.
14. Lacking regression tests for authn/authz, CSRF, JWT, and filter chains.
15. Leaving overrides from a CVE patch without an owner or expiration date.
16. Scanning only static source files without inspecting the actual JAR/image.
17. Failing to pin the Maven/Gradle wrapper, JDK, and repositories.
18. Assuming a BOM replaces security reviews or configuration testing.

## 18. Pre-Merge Completion Checklist

- [ ] Confirm Spring Boot version, JDK, Maven/Gradle wrapper, and support status.
- [ ] Specify whether the project uses Maven parent/BOM import or Gradle plugin/native platform.
- [ ] Use the exact BOM matching the Boot release.
- [ ] Starters/modules managed by the BOM have no unnecessary version pins.
- [ ] Review `spring-security.version` and `spring-framework.version` if overrides exist.
- [ ] Do not mix Security majors and Framework majors incompatible with Boot.
- [ ] Verify multiple BOM precedence.
- [ ] Maven: `effective-pom` and `dependency:tree` are clean.
- [ ] Gradle: `dependencies`/`dependencyInsight` are clean for runtime and test.
- [ ] Spring Security modules core/web/config/test/OAuth2 have consistent versions.
- [ ] Lockfiles and constraints do not hold outdated versions.
- [ ] Unit + MockMvc + integration security tests pass.
- [ ] SBOM, dependency scanning, and artifact provenance are in place.
- [ ] Every override has a justification, owner, review/expiration date, and rollback plan.
- [ ] Once a new BOM includes the fix, unnecessary overrides are removed.

### Self-Check Questions

1. How does a BOM differ from a starter?
2. Why does `spring-boot-starter-security` not need a version in a project with the Boot BOM?
3. What else does Maven `spring-boot-starter-parent` provide besides dependency management?
4. Why shouldn't a project importing a BOM expect `<spring-security.version>` to override it by default?
5. Which command shows the actual Spring Security modules in Maven?
6. How does `platform(...)` differ from `enforcedPlatform(...)`?
7. Do the Gradle dependency-management plugin and native platform use `ext['spring-security.version']` the same way?
8. When multiple BOMs exist, are Maven import order and Gradle dependency-management plugin import order identical?
9. Why shouldn't you pair Security 7.x with Boot 3.5.x just because it is newer?
10. How can you tell if a direct version was changed to another version by Gradle conflict resolution?
11. Why does `testRuntimeClasspath` also need to be reviewed?
12. Once the Boot BOM includes a patch, what should you do with a temporary override?
13. How do a lockfile and a BOM differ?
14. Why are SBOM/artifact scans still needed even after reviewing the dependency tree?

**Hints:** (1) BOM manages versions, starter pulls dependencies; (2) management supplies versions; (3) compiler/plugin defaults; (4) imported BOMs have property isolation, use `dependencyManagement`; (5) `dependency:tree`; (6) recommendation vs. strict enforcement; (7) no; (8) no; (9) compatibility/breaking changes; (10) `dependencyInsight`; (11) test modules must stay synchronized too; (12) remove the override and re-run tests; (13) locks record specific resolved versions; (14) binary artifacts can differ from expectations.

## 19. Official Documentation

- Spring Boot 3.5 Maven Plugin — parent and BOM import: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 Managed Dependency Coordinates: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Boot 3.5 Version Properties: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Security — Getting Spring Security: https://docs.spring.io/spring-security/reference/getting-spring-security.html
- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Platforms/BOM Import: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Spring Gradle Dependency Management Plugin: https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/

**Takeaway:** A BOM gives you a starting point of **co-tested dependencies**, but it does not replace verifying the **resolver-selected version**, integration testing, and override governance. When a bug or CVE is found, prefer **upgrading the appropriate Boot BOM**; only override with bounded scope, evidence, review, and a removal plan.
