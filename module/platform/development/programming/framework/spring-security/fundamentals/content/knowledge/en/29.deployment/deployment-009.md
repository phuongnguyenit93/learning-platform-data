# Updating Dependencies and Tracking Version-Accurate Patches in Spring Security

> **Scope:** deploying and operating **Java 17+, Spring Boot 3.x, and Spring Security 6.x** applications (Maven or Gradle). The focus is **knowing the exact dependencies in use, identifying which versions a security patch applies to, updating consistently, and proving the new build is deployed**. The guide covers inspecting the dependency graph, reading Spring Security Advisories/CVEs, a runnable Java/Gradle sample app, regression testing, BOM management, SBOMs, and pull-request automation. Versions shown in examples are **illustrative milestones cross-checked against official docs**, not a guarantee they remain the latest versions when you read this.

## 1. Why is updating dependencies security work?

An application using `spring-boot-starter-security` can run smoothly for years while carrying libraries with known vulnerabilities. When an advisory is published, the team must know **which code is affected, which packages live inside the artifact, and whether the fix is actually running in production**.

Never collapse these distinct questions into "I already edited `build.gradle`":

1. **Declared version:** which Spring Boot/plugin/library versions are declared in the build file?
2. **Managed version:** which versions are recommended by the BOM or dependency management?
3. **Resolved version:** which versions did Gradle/Maven ultimately select for `runtimeClasspath` or the dependency tree, including **transitive** dependencies?
4. **Packaged version:** which versions are actually packaged inside the executable JAR, WAR, container image, or native binary?
5. **Deployed version:** which build/image digest and library set are currently serving production traffic?
6. **Affected/fixed version:** what affected range, exploitation preconditions, and fixed versions does the official advisory specify?

A pull request changing a version **does not** mean production is patched. Likewise, a scanner warning "CVE present in repo" does not by itself prove exploitability in your active configuration; still, every finding must be **triaged with evidence**, never ignored just because the service "looks fine."

### Example dependency chain

```text
security-patch-demo
  |
  +-- org.springframework.boot:spring-boot-starter-security
  |      |
  |      +-- Spring Security Web / Config / Core / Crypto...
  |
  +-- org.springframework.boot:spring-boot-starter-web
         |
         +-- Spring Framework / embedded servlet container / JSON...
         |
         +-- Other transitive libraries

build.gradle declares starter without per-module version
       |
       v
Spring Boot BOM + Gradle resolution choose exact modules
       |
       v
bootJar packages a concrete runtime dependency set
       |
       v
Deployment rolls out a concrete image/artifact digest
```

Actual branches vary by Spring Boot line, modules, and starters chosen. This diagram illustrates **inventory accountability**, not the exact dependency tree output of one specific build.

## 2. How the Spring Boot BOM keeps versions aligned

### 2.1. What is a BOM?

A **Bill of Materials (BOM)** is a set of **version constraints/managed versions** for a cohesive set of dependencies. Spring Boot publishes `spring-boot-dependencies` to manage versions of Spring Framework, Spring Security, HTTP libraries, JSON, logging, databases, and more—ensuring a compatible set tested together by the Boot project.

In a typical Boot project, you declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

**There is no need to manually pin versions** on each starter or Spring Security module managed by the BOM when the plugin/dependency management is configured properly. Benefit: upgrading a **Spring Boot patch** generally pulls in an updated, aligned dependency set for that Boot line.

Important caveat: **applying the `org.springframework.boot` plugin alone should not be assumed to handle BOM management in every Gradle setup**. A Gradle project might use the `io.spring.dependency-management` plugin or native `platform(...)` to actually apply the BOM. When auditing, read the build script and resolved dependency graph rather than guessing from plugin names.

### 2.2. Patch, minor, and major releases are not identical

Example of a three-part version number:

```text
MAJOR.MINOR.PATCH

6.5.11
| |  |
| |  +--- Patch within a release line
| +------ Minor release line
+-------- Major generation
```

This is a **format-reading example**: never infer from the example number that `6.5.11` is currently deployed or the newest release. Spring Security describes patch releases as focusing on bug fixes and compatibility within a line, whereas major releases can introduce breaking changes. Even for a patch, **always run tests**, because a bug or security fix can alter flows that previously depended on broken behavior.

Spring Boot 3.x typically pairs with Spring Framework 6.x and Spring Security 6.x managed by that Boot line's BOM. When moving to a newer Boot generation, read the migration guide, Java/Gradle/Maven requirements, and API changes rather than bumping individual libraries to a higher major version blindly.

### 2.3. The "right version" is supported and contains the fix

No **single** version number guarantees safety for every app. A suitable version must satisfy all of the following:

- Belongs to a **release line still receiving fixes under the support policy** governing your organization.
- Is **outside the affected range** of relevant advisories, or meets the **fixed version** and any extra guidance in the advisory.
- Is compatible with Spring Boot/Spring Framework/Security, Java runtime, Gradle/Maven, Servlet container, and extensions in use.
- Has **actually been resolved and packaged**, not merely edited in a dependency declaration.
- Has passed tests for authentication, authorization, CSRF, sessions, headers, and critical business workflows.
- Is deployed across all instances with verified build/image versions or digests.

If no patch exists on your current line, evaluate upgrading to a **supported** minor/major release or applying vendor-recommended temporary mitigations with explicit upgrade deadlines and exception tracking.

## 3. A decision flow when a CVE/advisory lands

```text
New notification received
      |
      v
Confirm official source / disclosure date / package / advisory ID
      |
      v
Fetch RESOLVED dependency graph for the deployed build version
      |
      +-- Module/package absent? -> record evidence, inspect artifact/runtime
      |
      +-- Module in affected range?
            |
            +-- No  -> store version evidence, keep monitoring
            |
            +-- Yes -> check affected conditions,
                       attack surface, exposed entry points, controls
                       |
                       v
             Fixed release on supported line?
                 |                     |
                Yes                   No
                 |                     |
                 v                     v
          Bump patch/BOM        Upgrade release line
          or vendor fix         or time-bound mitigation
                 \                     /
                  v                   v
                Build + tests + scan + inspect artifact/SBOM
                              |
                              v
               Approval, canary, release, monitor
                              |
                              v
                  Verify all production instances
```

**Evidence-based triage, never guesswork:** an advisory may apply only when a specific feature, filter chain, or untrusted-input API is enabled. Always read **affected versions, fixed versions, configuration preconditions, impact description, and remediation notes**. If scope is not yet verified, keep status as "under investigation" and apply appropriate protections; never mark "not affected" without evidence.

CVSS/EPSS scores, exploit availability, Internet exposure, required privileges, and affected assets/data help **prioritize remediation**. They do not replace verifying exact components and affected ranges; high severity does not mean every usage is exploitable, and low severity does not justify indefinite deferral.

## 4. Official sources to monitor

| Source | Used to verify | What not to infer |
| --- | --- | --- |
| [Spring Security Advisories](https://spring.io/security/) | Published advisories, product/module, CVE, severity, affected/fixed versions | Do not read only the title or pick the highest version without checking support status |
| [Spring Boot Releases / Docs](https://spring.io/projects/spring-boot) | Release lines, reference docs, upgrade guides, matching BOMs | "A newer version exists" does not mean safe to deploy without testing |
| [Spring Security release documentation](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html) | Numbering, starters, overrides, BOMs | Overriding one module arbitrarily can cause module skew |
| [Spring Boot Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) | Exact coordinates managed by that **exact** Boot patch's BOM | Do not assume runtime uses the managed version if overrides/conflicts exist |
| [Gradle dependency reports](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) | Why version X was chosen on configuration Y | One configuration does not represent every production artifact |
| [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html) | Resolved dependency tree | Does not reflect other artifacts without checking scopes/modules/packaging |
| [GitHub Advisory Database](https://github.com/advisories) and [OSV](https://osv.dev/) | Cross-ecosystem vulnerability data | Scanners may report false positives or miss preconditions; triage is required |
| [NVD](https://nvd.nist.gov/) | CVE metadata, scoring, and external references | Never use as the sole source when vendor advisories have newer guidance |

**Operational cadence:** monitor Spring security advisories continuously via RSS/notifications/approved channels, and review dependency PRs on schedule. For urgent advisories, act immediately based on risk instead of waiting for periodic upgrade windows.

### Key questions when reading an advisory

1. Does the CVE/advisory belong to **Spring Security**, Spring Framework, Boot, Spring Data, Tomcat, Jackson, Logback, or another module?
2. What is the exact **artifact** name? Is it pulled into the build via a starter or transitive dependency?
3. What are the affected version ranges and fixed versions **per release line**?
4. Must a specific configuration, endpoint, or feature be enabled to be vulnerable?
5. Is the patch already included in your current Boot BOM, or must you bump the Boot patch or apply controlled dependency management?
6. Do all environments resolve the same artifact? Do test and production differ in image or version?
7. Is a restart/redeploy required to replace the vulnerable JAR?
8. Are there vendor-approved temporary mitigations? Who approves exceptions and when do they expire?

## 5. Complete Gradle project to practice patch verification

### 5.1. Lab goal

Build a small API with:

- `GET /public` — public.
- `GET /api/me` — requires HTTP Basic authentication.
- `GET /api/admin` — `ROLE_ADMIN` only.
- Two demo accounts `reader`/`reader-pass` and `admin`/`admin-pass` with BCrypt-hashed passwords.
- Regression tests for 200, 401, and 403 paths.
- Build using the **Spring Boot BOM** rather than pinning individual Spring Security modules.

**Version used in this sample:** `org.springframework.boot` plugin `3.5.16` is an example patch version present in official Spring Boot 3.5 documentation when this guide was authored. It is **not a directive for every project to downgrade/upgrade to 3.5.16**, nor should you assume it remains the latest patch. In real projects, **check the release docs for your supported line and verify advisory fixed versions before changing versions**.

### 5.2. Project structure

```text
security-patch-demo/
├── settings.gradle
├── build.gradle
├── gradlew                      # generated by Gradle Wrapper
├── gradlew.bat                  # generated by Gradle Wrapper
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/SecurityPatchDemoApplication.java
    └── test/java/demo/SecurityPatchDemoApplicationTest.java
```

`gradlew`, `gradlew.bat`, and `gradle/wrapper/` are **wrapper files generated by Gradle tooling** (e.g., Spring Initializr). They are not created by pasting the snippets below; initialize a Boot/Gradle project first or generate the Gradle Wrapper with an installed Gradle.

### 5.3. settings.gradle

```groovy
rootProject.name = 'security-patch-demo'
```

### 5.4. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'demo'
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
    // Native Gradle BOM support; do not use the
    // io.spring.dependency-management plugin in this variant.
    implementation platform(
            org.springframework.boot.gradle.plugin
                    .SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(
            org.springframework.boot.gradle.plugin
                    .SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Two points to read carefully:**

1. The `org.springframework.boot` plugin is pinned to a concrete version instead of `3.5.+` or `latest.release`. This makes builds more reproducible, though transitive versions, Gradle Wrapper, and artifact repositories still need checking.
2. `implementation platform(...)` and `testImplementation platform(...)` apply Boot's BOM to **both configuration families** in this project. Using Gradle's native BOM support is a supported alternative to `io.spring.dependency-management`, which is why `spring-boot-starter-security` and `spring-security-test` carry no explicit version strings.

**Do not blindly swap `platform` for `enforcedPlatform`.** `platform` contributes constraints/recommendations to resolution; another dependency's constraints or overrides can shift the selected version away from the BOM. `enforcedPlatform` forces versions and can conflict with other dependencies. Inspect `dependencyInsight` and decide based on compatibility, never on a hunch that "forcing harder is safer."

### 5.5. Runnable Java 17+ application

Create `src/main/java/demo/SecurityPatchDemoApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityPatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityPatchDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("name", authentication.getName());
    }

    @GetMapping("/api/admin")
    String adminPage() {
        return "admin-only";
    }
}
```

The file contains exactly one `public` class matching the file name, plus two package-private classes in package `demo`. `@SpringBootApplication` scans both the controller and configuration. The API exposes only GET routes without disabling CSRF; its goal is verifying **security behavior remains intact after upgrading dependencies**, not demonstrating a full production authorization setup.

### 5.6. Regression testing with JUnit and MockMvc

Create `src/test/java/demo/SecurityPatchDemoApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPatchDemoApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointStillWorksAfterUpgrade() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordStillFails() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("reader"));
    }

    @Test
    void normalUserStillCannotReadAdminEndpoint()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminStillHasExpectedAccess() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-only"));
    }
}
```

These are **functional regression smoke tests**: they confirm the demo's authentication/authorization policy still works after updates. They **do not prove** all CVEs are resolved; that requires matching advisory affected/fixed versions against resolved/packaged artifacts, testing affected preconditions, and deploying for real.

### 5.7. Running the project

With a compatible Gradle Wrapper and JDK 17:

```bash
./gradlew --version
./gradlew clean test bootJar
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
.\gradlew.bat bootRun
```

When the server runs at `http://localhost:8080` by default:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

Expected statuses are 200, 401, 200, 403, and 200 respectively with the example's HTTP Basic setup. JSON key ordering may differ; HTTP statuses and security decisions are the focus. **Never use demo accounts or hardcoded passwords in production.**

## 6. Measuring actual resolved versions with Gradle

### 6.1. Inspecting runtimeClasspath

Run:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

The report lists resolved dependencies for `runtimeClasspath`, including direct and transitive ones. Inspect `org.springframework.security`, `org.springframework`, the embedded server, JSON, logging, and any advisory-related modules.

**Never judge versions by eyeballing `build.gradle`**: constraints can pick a version different from what you assume. When seeing `requested -> selected`, the **selected** version is the one entering the runtime configuration.

### 6.2. Tracing why Spring Security Web chose a version

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-web \
  --configuration runtimeClasspath
```

This command explains the **dependency path**, selected version, and selection reason. Also check:

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework:spring-web \
  --configuration runtimeClasspath
```

Backslashes `\` are Bash line continuations; in PowerShell, write on **one line** or use PowerShell's line continuation:

```powershell
.\gradlew.bat dependencyInsight --dependency org.springframework.security:spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
```

**Distinguish configurations:** `runtimeClasspath` reflects normal Java application runtime; `testRuntimeClasspath` adds `spring-security-test`, JUnit, and test-only libraries. Plugins, annotation processors, and build tool classpaths live in separate configurations. A library on the test classpath is not necessarily in the production JAR; a library used only by a build plugin is not necessarily in app runtime.

### 6.3. Inspecting packaged artifacts, not just the graph

After running `bootJar` on the example project, the file name follows `settings.gradle` and `version`:

```bash
jar tf build/libs/security-patch-demo-0.0.1-SNAPSHOT.jar \
  | grep 'BOOT-INF/lib/spring-security-'
```

On PowerShell:

```powershell
jar tf build/libs/security-patch-demo-0.0.1-SNAPSHOT.jar |
    Select-String "BOOT-INF/lib/spring-security-"
```

Actual file names vary if the project customizes `bootJar` or `version`. Check `build/libs` rather than guessing from a tutorial. For Boot executable JARs, `BOOT-INF/lib` holds runtime dependency JARs; for WARs, native images, shaded JARs, or other packaging pipelines, adapt inspection accordingly.

**If `dependencyInsight` shows the fixed version yet the executable JAR still holds the old version**, packaging/repackaging or CI caching is broken. If the JAR is right yet containers run the old version, the fault lies in image build, push, or deployment rollout. Verify every layer with evidence.

### 6.4. Dependency locking for reproducibility

If the project adopts Gradle dependency locking, add to `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

This is a **configuration snippet to add to the project**, not a standalone Gradle file. Then generate/refresh lock state for resolved configurations:

```bash
./gradlew dependencies --write-locks
./gradlew clean test
```

Commit generated lockfiles so CI and developers resolve identical versions. When upgrading a BOM/patch, **update the lockfile in the same pull request**; if a lock pins an old version, bumping the plugin without updating the lock can cause resolution failures or keep old dependencies via constraints. Locking ensures reproducibility—**it does not automatically detect or patch vulnerabilities**. Avoid dynamic versions like `6.+` so CI never upgrades silently outside code review.

In multi-module/multi-configuration builds, verify all configurations used for building and deploying are resolved and locked. Gradle docs detail locking limitations (such as buildscript dependencies or SNAPSHOT/changing modules) and selective lock updates.

## 7. Maven projects: checking the dependency tree and managed versions

In Maven projects, **`spring-boot-starter-parent`** typically supplies dependency management matching the Boot version. Illustrative `pom.xml`:

```xml
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

    <groupId>demo</groupId>
    <artifactId>security-patch-demo</artifactId>
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

This is the Maven equivalent for the same Java/test app in section 5; **pick either Maven or Gradle** rather than keeping two build files in one project without a specific reason.

Use the Maven Wrapper (`mvnw`) if available:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw clean verify
```

In PowerShell or Windows Command Prompt, run `mvnw.cmd`. `dependency:tree` displays the actual resolved graph and transitive paths; `effective-pom` shows parameters and managed dependencies after Maven merges parent, profiles, BOMs, and inheritance. `effective-pom.xml` is an inspection output—do not confuse it with a production artifact or overwrite `pom.xml` with it.

If you import `spring-boot-dependencies` directly inside `dependencyManagement` instead of inheriting the Boot parent, verify both the BOM import and plugin versions explicitly; a BOM manages **dependency versions**, not every Maven build plugin the way the parent POM does.

## 8. Safe update strategies when an advisory drops

### 8.1. Case A: the fix is already in a matching Boot patch

Preferred workflow:

1. Identify the app's current Boot version and supported line.
2. Read the advisory: library, affected range, fixed version, and prerequisites.
3. Check the **Managed Dependency Coordinates** table for the target Boot patch.
4. Bump the **Boot patch** in the build file or parent POM so Boot's BOM picks a consistent dependency set.
5. Verify via `dependencyInsight`/`dependency:tree` that the affected module resolves to the fixed version.
6. Run tests, package the artifact, scan dependencies, canary-deploy, and verify the artifact in runtime.

This path usually requires the fewest manual per-library overrides. Still, never assume every new Boot patch fixes **every** CVE—always cross-check the exact module and fixed version.

### 8.2. Case B: Spring Security has the fix, but the Boot BOM has not caught up yet

A **controlled override** may be needed in urgent cases. Never blindly add:

```groovy
// COUNTER-EXAMPLE: easily causes Spring Security module version skew.
implementation 'org.springframework.security:spring-security-web:7.0.0'
```

This is a **non-runnable counter-example**: forcing a higher major version for one module inside a Boot 3.x app can trigger API/linkage conflicts or behavior changes. Across Spring Security modules, maintain version alignment via the Spring Security BOM and official guidance. For Spring Framework, also check compatibility requirements.

In a Maven project inheriting Boot's parent, Spring Security docs allow overriding the Boot-managed Security version via `spring-security.version`, **once fixed versions and compatibility are verified**:

```xml
<properties>
    <java.version>17</java.version>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
```

This is an **illustrative config snippet**, not a recommendation to pin `6.5.11` for every CVE. In Gradle with `io.spring.dependency-management`, the corresponding managed property works similarly. However, with **native `platform(...)`** as in section 5, Maven-style properties **do not automatically override BOM constraints**; use Gradle constraints, platforms, or resolution mechanisms per official docs.

Every emergency override must be documented: reason/advisory, approver, target fixed version, affected modules, dependency graph output, tests, review date, and a plan to **remove the override once the official BOM catches up**. If the issue touches Spring Framework, the servlet container, or another transitive library, upgrade cohesively per vendor guidance instead of forcing `spring-security-web` alone.

### 8.3. Case C: the project sits on a release line no longer receiving patches

You cannot solve this by "updating to the latest patch" if **the old line receives no fixes**. You must:

- Check OSS/commercial support timelines and which lines still receive vendor fixes.
- Plan an upgrade to a supported major/minor version, including Java, Gradle/Maven, framework, and Servlet requirements.
- Assess breaking changes: Security DSL APIs, matchers, filter chains, and session/authentication behavior.
- Apply temporary mitigations **validated against the advisory**: narrow attack surface at the gateway, disable affected features, add targeted rules, or apply rate limits/traffic controls where helpful.
- Record risk acceptance with an explicit owner and expiration date; never add permanent scanner waivers.
- Re-test all security flows and critical business workflows.

Self-maintained backports without vendor support require dedicated review, testing, and distribution rigor; you cannot patch a few lines of source and declare "CVE resolved."

## 9. Evaluating transitive dependencies and classpath drift

### 9.1. Direct vs. transitive dependencies

Suppose a project declares only `spring-boot-starter-web`, yet a servlet/logging/JSON library enters transitively. When a CVE hits one of those libraries:

- Use `dependencyInsight` or `dependency:tree` to find **what pulls it in**.
- Verify whether it actually enters `runtimeClasspath` and the production artifact.
- Check whether a newer Boot patch manages the fixed version.
- If multiple upstreams bring the same package, inspect **resolution conflicts** and the winning version.
- If the package is unused on vulnerable code paths, document exploitability conditions and check scanner/advisory notes rather than excluding blindly.

Some vulnerabilities affect **build-time tools, tests, or plugins**. They can still impact supply chain/CI, though exposure differs from runtime servers. Classify scope accurately instead of assuming "not in runtime" always means harmless.

### 9.2. Forced overrides can compile yet fail at runtime

Common symptoms of skewed module versions:

- `NoSuchMethodError`, `NoClassDefFoundError`, or class linkage errors at startup or on rarely hit endpoints.
- Subtle CSRF/authentication/authorization behavior shifts from bug fixes.
- Servlet container or Spring Framework minimum API version mismatches.
- Behavioral changes in JSON serialization, validation, or test libraries.
- One Spring Security module upgraded while `spring-security-config`/`core`/`web` stays old.
- Lockfiles or dependency constraints unintentionally holding an old version.

**How to avoid:** inspect the resolved runtime tree, run real runtime tests, build the JAR/container, and run behavioral tests. Never use `exclude` or `force` to "make the scanner green" if doing so strips security filters, codecs, or required modules.

### 9.3. SBOM: recording components per artifact

A **Software Bill of Materials (SBOM)** such as CycloneDX captures dependency components, versions, and hashes for a build. Spring Boot documents integrating CycloneDX Maven/Gradle plugins; CI can emit an SBOM tied to each artifact/image digest and archive it as evidence when new advisories arrive.

An inventory workflow:

```text
Build commit SHA + toolchain + dependency lock
        |
        v
Resolve dependency graph (runtimeClasspath)
        |
        v
Build bootJar/container image
        |
        v
Generate/export SBOM for the artifact
        |
        v
Store artifact hash/image digest + SBOM + build provenance
        |
        v
Scan/advisory match + triage + release approval
```

**An SBOM is not an automatic scanner**, nor does a scanner automatically understand every exploit precondition. Tie each SBOM to a concrete build rather than keeping one generic "repo SBOM" disconnected from deployed artifacts.

### 9.4. Inspecting containers and multiple environments

Beyond Spring dependency JARs, a container holds a **base image**, OS packages, a JRE, and agents/sidecars. A security advisory in OpenSSL/glibc/JRE is not fixed by bumping Spring Security. Conversely, bumping the base image does not update `spring-security-web` inside your JAR unless the Java build changes.

To conclude production is patched, verify:

- Running image tags and **digests** (tags can be overwritten; digests identify exact content).
- Which digest each environment, region, and instance runs—including background workers.
- The SBOM/dependency graph tied to that build digest.
- Whether old pods, replicas, or blue/green slots still serve traffic.
- Whether image/build caches could reintroduce stale artifacts.
- Whether deployment rollbacks could redeploy a vulnerable version; maintain an allowed-digest list.

## 10. Update automation: Dependabot, Renovate, and review

### 10.1. Automate pull requests, never blindly auto-merge

Tools like **Dependabot** or **Renovate** detect patch/minor updates, update build files/lockfiles, and open PRs. This keeps projects from drifting months behind. However, **opening a PR does not prove a patch is deployed**; owning engineers must still check advisories, compatibility, and tests.

Example `.github/dependabot.yml` for a Gradle and GitHub Actions project:

```yaml
version: 2
updates:
  - package-ecosystem: "gradle"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

This is a **Dependabot version-updates config sample**: the repository must enable the required GitHub features/permissions, and security-update PRs/alerts have separate settings. Real configs should account for multi-module directories, private registries, grouping, branch protections, cooldowns, labels, and codeowners. Even with automated PRs, CI must pass and human reviewers must read changelogs/release notes.

**Never rely on a weekly schedule as your sole SLA for urgent CVEs.** Security alerts/advisories need dedicated notification and escalation paths capable of raising out-of-band PRs.

### 10.2. Dependency update PR review checklist

For bot- or developer-opened PRs, reviews should check:

| Check | Evidence to keep |
| --- | --- |
| What changed in the version manifest? | Diff of `build.gradle`/`pom.xml`, plugin/parent/BOM |
| What version actually resolved? | `dependencyInsight` or `dependency:tree` on the right configuration |
| Does the CVE-affected module have a fixed version? | Official advisory + fixed version + graph |
| Did lockfiles/SBOM update consistently? | Lockfile diff, new SBOM, and build metadata |
| Do security tests still pass? | 200/401/403, CSRF, sessions, method security, OAuth/OIDC if used |
| Functional regressions? | Unit/integration/e2e, database/client compatibility |
| Which binary artifact was built? | JAR metadata/hash and/or image digest |
| What is the rollout plan? | Canary, smoke tests, metrics, rollback, incident owner |
| Any overrides/waivers? | Justification, approver, deadline, and tracking |

Non-Spring dependencies like JDBC drivers, Redis clients, or messaging SDKs can often bump independently per risk. For Spring Security/Framework, prefer **keeping module groups aligned** per BOM/vendor guidance.

### 10.3. No need to manually pin every transitive library

Pinning dozens of versions in build files creates "version soup," defeating Boot's BOM and making future patch upgrades painful. Instead:

- Pin the **Spring Boot plugin/parent** to a concrete release.
- Let the BOM manage supported dependencies.
- Use lockfiles for reproducibility and update them under review.
- Override only with documented justification, advisory comments, and an expiration date.
- Separate test/build-time/runtime dependencies when identifying affected components.

**Never use `+`, `LATEST`, or dynamic wildcards** thinking it "auto-secures" builds: they make builds shift silently without diffs or reviews, risk breaking changes, and offer zero deployment guarantees.

## 11. A verifiable CI/CD patching pipeline

### 11.1. Recommended verification flow

```text
Advisory / bot PR / scheduled review
      |
      v
Read source + affected/fixed version + preconditions
      |
      v
Change Boot patch/BOM or approved override
      |
      v
Dependency graph and lockfile verification
      |
      v
Unit tests + MockMvc security tests
      |
      v
Integration/E2E + SCA/dependency scan + SBOM
      |
      v
Build immutable artifact + provenance
      |
      v
Stage deployment + smoke security regression
      |
      v
Canary + metrics + review
      |
      v
Production rollout, verify every instance/image digest
      |
      v
Close advisory ticket with evidence + monitoring
```

### 11.2. Essential quality gates

**Build gate:** verified Java toolchain/Gradle/Maven versions, clean build, resolved dependency graph, signature/checksum policies, and trusted repositories.

**Security regression gate:** tests verify anonymous access to private endpoints is blocked; wrong credentials return 401 (HTTP Basic) while valid users get 200; under-privileged users get 403 while admins get 200. Real apps also test session logout/fixation, CSRF, OAuth2 Resource Server token validation, method security, filter-chain ordering, and multi-tenant resource policies.

**Dependency gate:** scanner flags vulnerable packages/versions; triage severity and exploitability rather than hiding/disabling all warnings. Approved exceptions carry advisory IDs, rationale, expiration dates, and owners.

**Packaging gate:** executable JAR contains the right Spring Security modules; SBOM/hash matches the freshly built artifact; containers contain no stale cached layers or cross-pipeline artifacts.

**Deployment gate:** verify running versions/digests rather than trusting "deploy succeeded" logs; run staging/canary smoke tests and watch 401/403/500 counts, login rates, token refreshes, latency, and anomalies.

### 11.3. Safe rollout

A security filter patch can change how URL encodings, matchers, or CSRF tokens behave. Rollouts should include:

1. Deploying to staging with representative configuration and test accounts.
2. Comparing authentication/authorization success/failure rates before and after.
3. Canarying a slice of traffic where architecture permits.
4. Having a rollback or roll-forward playbook **that never accidentally rolls back to a vulnerable build**. If safe rollback is impossible, prepare a hotfix or compensating mitigation.
5. Avoiding backward-incompatible database/schema migrations while old and new versions run concurrently.
6. Recording release metadata: commit, build ID, BOM/runtime versions, SBOM digest, target environment, approver, and deploy timestamp.

**Avoid auto-merging dependency PRs solely on "green tests"** when changes touch authentication, authorization, or critical vulnerabilities. Tests may miss behavioral nuances or altered security defaults; apply risk-appropriate human review.

## 12. Diagnosing common Spring Security update issues

### 12.1. "I updated build.gradle, but the scanner still reports the CVE"

Check in order:

- Did the plugin/parent version change while a **lockfile** pinned the old version?
- Does the app use native BOM or `io.spring.dependency-management`? Are there subproject overrides?
- Does `dependencyInsight` select the fixed version, or did another constraint override it?
- Is the scanner inspecting `testRuntimeClasspath`, `runtimeClasspath`, build plugins, or a **stale image**?
- Was a fresh artifact/container built? Did the cluster's image digest actually change?
- Is the scanner report cached, aliasing components, or flagging a false positive needing evidence review?
- Does the CVE affect the newer module/line or only specific configuration preconditions?

Never slap on an `exclude` just to silence a scanner without knowing whether the module still ships in the artifact.

### 12.2. "Bumping spring-security-web caused NoSuchMethodError at runtime"

Likely Spring Security/Spring Framework modules are skewed, or compile and runtime classpaths differ. Trace all `org.springframework.security` and `org.springframework` modules in the dependency graph; restore Boot BOM or approved Security BOM alignment, remove unnecessary overrides, run integration tests, and clean-build. Never bump one module to a different major version just because it looks "newer."

### 12.3. "CI is green, yet deployment is still vulnerable"

Possible causes: built from the wrong commit, container copied a stale JAR, mutable image tag reused, un-rotated blue/green slot, or partial rollout. Compare commit hash, artifact digest, image digest, and live instances. **A passing CI run is one piece of evidence, never the sole proof of production state.**

### 12.4. "It's only a transitive library, so we can ignore it"

False. Vulnerabilities can still be exploited through transitively loaded libraries. Check scope, reachable code paths, and fixed versions rather than treating "not directly declared" as immunity.

### 12.5. "A CVE in a test dependency is identical to a server CVE"

Not quite. Test/build-tool vulnerabilities threaten CI and supply chains, whereas runtime CVEs threaten production services. Assess each in its own environment. Still, never assume test dependencies are harmless if CI processes untrusted code/inputs or holds sensitive credentials.

### 12.6. "Patches are always compatible and safe to merge immediately"

Patches break things less often, yet security fixes can tighten previously permissive checks, breaking tests that relied on insecure behavior. Run regression tests, read release notes and new policies, and fix app behavior properly—**never slap on `permitAll` just to make tests pass**.

### 12.7. "The BOM is safe, so every dependency in the project is safe"

A BOM is a curated set of managed versions, not a certificate of zero CVEs. Projects may add non-BOM libraries, overrides, custom plugins, OS packages, image layers, or other scopes. Perform end-to-end inventory.

## 13. Version operations and patch-tracking checklist

1. Every service has an **owner**, repository, deploy environments, build pipeline, inventory/SBOM, and supported-line record.
2. Pin concrete Boot plugin/parent versions; verify Java/Gradle/Maven toolchain compatibility.
3. Verify the active Boot BOM, Gradle native platform, or Maven dependency management mechanism.
4. `spring-boot-starter-security` does not manually pin individual modules when the BOM manages them cohesively.
5. Capture the resolved `runtimeClasspath` graph or Maven dependency tree for deployed builds.
6. Record packaged modules and artifact/image digests; separate test/build-time from runtime.
7. Track Spring Security Advisories alongside Framework, Boot, server/container, and transitive library advisories.
8. For every alert, inspect affected ranges, fixed versions, prerequisites, and exploitability.
9. Triage by risk/scope and evidence; never suppress scanner alerts indefinitely.
10. Prefer upgrading the Boot patch/BOM on a supported line; overrides need rationale, approval, and expiration dates.
11. Lockfiles, SBOMs, and dependency diffs match the exact commit and build.
12. CI runs regression tests for login, roles, CSRF, method security, sessions/JWTs, and critical business flows.
13. Verify `bootJar`/images actually contain the fixed modules.
14. Canary-deploy to staging/prod, monitor 401/403/500 metrics, and keep safe rollbacks ready.
15. Verify **all** production instances switched digests, including workers and batch jobs.
16. Close tickets with advisory IDs, impact, fixed versions, build/deploy evidence, timestamps, and approvers.
17. Maintain regular version-update cadences alongside a separate urgent CVE escalation channel.
18. Periodically review end-of-support dates; never linger on unpatched release lines without a migration plan.
19. Update playbooks, test evidence, and security policies on minor/major upgrades.
20. Never log secrets while investigating versions/CVEs; store artifact hashes and correlation IDs instead of passwords/tokens.

## 14. Practice exercises

1. Why doesn't `spring-boot-starter-security` need manual version pins on `spring-security-web`/`core` when using the Boot BOM properly?
2. Distinguish declared, managed, resolved, packaged, and deployed versions. Which tool or source verifies each?
3. An advisory flags library X on `runtimeClasspath`, yet `build.gradle` never declares X. Why might that happen?
4. When `dependencyInsight` shows `selected` differs from `requested`, what details should you inspect?
5. If you bump the Boot patch without updating the lockfile, what might happen in CI?
6. Why shouldn't you upgrade `spring-security-web` to a newer major version while other Security modules remain on an older line?
7. A CVE is exploitable only when a certain configuration is enabled. What evidence is needed to mark the service unaffected, and who should approve it?
8. If no fixed release exists on your current supported line, what options remain?
9. Why is `./gradlew test` passing insufficient to prove production is no longer vulnerable?
10. Why does updating the JRE/base image not equal updating dependencies inside `BOOT-INF/lib`?
11. Draft a PR review checklist for a patch affecting the CSRF filter and HTTP request matchers.
12. Which tests quickly catch accidentally relaxed Spring Security permissions after an upgrade?
13. How does an SBOM differ from a vulnerability scanner? Why bind SBOMs to image digests/build IDs?
14. Why can't weekly automated dependency-update PRs replace an urgent advisory response workflow?
15. If a scanner flags a CVE after release and the rollback target is also vulnerable, what should the team do instead?
16. With the Maven Boot parent, what does `spring-security.version` do? Why doesn't that exact property apply automatically to Gradle's native `platform(...)`?
17. Why is an end-of-support release line risky even when no public CVE has been disclosed against it yet?
18. Describe the minimum evidence proving **a specific vulnerability is patched across all of production**.

**Hints:** (1) BOM manages aligned versions; (2) manifest/BOM/graph/JAR/container; (3) transitive dependency; (4) constraints/conflicts/paths; (5) stale lockfile can fail resolution or retain old versions; (6) API, linkage, and support skew; (7) real config, exposed paths, advisory preconditions, and review; (8) upgrade to a supported line or apply time-bound mitigations; (9) must check packaged artifacts, deployment, and CVE conditions; (10) separate layers; (11) matcher/CSRF/security regressions, resolved versions, and rollout; (12) anonymous, role, object-owner, cross-tenant, and unsafe-method tests; (13) inventory vs. detection; (14) urgent SLA; (15) targeted mitigation or safe roll-forward; (16) parent properties vs. Gradle constraints; (17) no future patches; (18) advisory fixed versions + build provenance + image digest + all running instances.

## 15. Official documentation

- [Spring Security — Security Advisories](https://spring.io/security/)
- [Spring Security 6.5 — Getting Spring Security, BOM and release numbering](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Customize Dependency Versions and SBOM](https://docs.spring.io/spring-boot/how-to/build.html)
- [Spring Boot 3.5 — Gradle Plugin Dependency Management](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Apache Maven — Dependency Plugin and dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [GitHub Docs — Dependabot Version Updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates)
- [GitHub Docs — Configuring Dependabot Version Updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-version-updates)
- [OWASP — Dependency-Check](https://owasp.org/www-project-dependency-check/)
- [CycloneDX — Software Bill of Materials](https://cyclonedx.org/)