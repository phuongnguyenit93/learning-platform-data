# Reading the Right Version-Pair Migration Guide and Managing Dependencies with a BOM

> **Context:** Java 17+, Spring Security **Servlet**, Spring Boot, Maven/Gradle. Upgrading safely is not just bumping version numbers until the build succeeds. You need to pick the **right source → target pair**, use the migration guide that matches that pair, manage related dependencies consistently with a BOM, and re-test the security behavior of the HTTP filter chain.
>
> **Note on versions:** Numbers such as Spring Boot `3.5.0` and Spring Security `6.5.0` in the syntax examples are **illustrative versions only**, not a claim about the latest release or a rigid directive for your project. Before an actual upgrade, verify the supported releases, the managed dependencies of **your exact Spring Boot target**, and the resolved dependency graph in the build.

## 1. Why can't you just “upgrade Spring Security to the latest version”?

A Spring Security Servlet application runs within an ecosystem consisting of:

- **JDK** for compilation and runtime.
- **Spring Boot**: auto-configuration, starters, managed dependencies, and packaging.
- **Spring Framework**: Web MVC, DI, AOP, transactions, and HTTP abstractions.
- **Spring Security**: authentication, authorization, Servlet filters, sessions, and OAuth2.
- **Servlet container/Jakarta API**: Tomcat/Jetty/Undertow, `jakarta.servlet.*`.
- **Additional libraries**: Spring Session, Spring Cloud, JPA, OAuth client/resource server, JWT, SAML, and the test framework.

These components must be **compatible at runtime**. For example, a Maven module compiled against `spring-security-config` from a newer release that pulls in an older `spring-security-web` or `spring-core` at runtime can cause `NoSuchMethodError`, `NoClassDefFoundError`, or altered filter behavior.

Conversely, resolving every artifact still **does not prove** the system is secure: changes in Spring Security defaults can cause `/api/**` to return a form-login redirect instead of a Bearer 401, handle CSRF differently, or fail to select a custom `SecurityFilterChain`.

**The right workflow:** know your actual versions → identify the target release → read the source-to-target migration guide → align dependencies through one consistent management source → inspect resolved versions → run security regression tests.

## 2. What does “version pair” mean?

It is not just a pair of old and new `spring-security-core` versions. You need to record a **compatibility matrix** for the entire application.

| Component | Source version to measure | Target version to identify | Risk if guessed |
| --- | --- | --- | --- |
| Java runtime/toolchain | JDK in CI and container | Minimum Java of target Boot | Build passes in IDE, fails at runtime |
| Spring Boot | Actual parent/BOM/plugin release | Boot release chosen by organization | Auto-config/starter changes |
| Spring Framework | Resolved `spring-*` artifacts | Version managed by target Boot | API incompatibility |
| Spring Security | Resolved `core`, `web`, `config`, OAuth2, test | Branch/patch managed by target Boot | Mismatched Security filters/DSL |
| Servlet/Jakarta | Current Servlet API and container | Container compatible with target Boot | `javax`/`jakarta` mismatch |
| Related modules | Session, Cloud, Data, OAuth, SAML | Compatible release train | Config/classpath mismatch |
| Test tooling | `spring-security-test`, JUnit, MockMvc | Test artifacts aligned with target stack | False tests/runtime errors |

Examples of **upgrade paths**, rather than a single fixed pair:

1. **Patch update** within the same Boot branch: review release notes, security advisories, dependency changes, and tests.
2. **Minor update** Boot 3.x → Boot 3.y: read the upgrading/release notes for the target minor release and the corresponding Security release.
3. **Major update** Boot 2.7 → Boot 3.x: read Boot 2→3, Security 5→6, Framework/Jakarta guidance, and upgrade Java to the required baseline.
4. **Next major** Boot 3.x → later branch: read the **guide for the exact source/target pair**; do not mechanically repeat the 2→3 checklist.
5. **Non-Boot Spring app** using Security directly: you can use the Security BOM, but you must still verify Framework/Servlet compatibility separately.

Do not assume “Boot 3 is always tied to one fixed Security 6.y version” across every patch or minor release. The final version is the outcome of **managed dependencies and dependency resolution**; verify it in practice.

## 3. Distinguishing declared dependencies from resolved dependencies

A Maven snippet:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Omitting `<version>` can be **correct and recommended** when the Maven project inherits from `spring-boot-starter-parent` or imports `spring-boot-dependencies`. The version is supplied by dependency management.

Conversely, writing:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>6.5.0</version>
</dependency>
```

inside a Boot app that already manages Security can inadvertently **override** the version expected by the target Boot release. Avoid pinning individual module versions arbitrarily.

You should distinguish between:

- **Declared**: the dependency as declared in the build file.
- **Managed**: the version suggested/managed by a BOM or parent.
- **Resolved**: the final version chosen by the build tool after evaluating the dependency graph, constraints, and overrides.
- **Runtime**: the libraries actually deployed and loaded by the classloader.

These are not four terms for the same data. Only the **dependency tree / effective POM / Gradle insight** provides evidence of resolved versions; `pom.xml` declarations or an IDE view alone are not enough.

## 4. Verifying the baseline before choosing a migration guide

### 4.1. Maven

Run at the root of the Maven project (and for multi-module builds, check the deployable modules as well):

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:tree "-Dincludes=org.springframework.security:*"
mvn dependency:tree "-Dincludes=org.springframework:*"
mvn dependency:tree "-Dincludes=org.springframework.boot:*"
mvn clean verify
```

**How to read the output:**
- Are `spring-security-core`, `spring-security-web`, `spring-security-config`, and `spring-security-test` on the same release line/version?
- Is any dependency or `dependencyManagement` entry pinning a different version from the BOM?
- Do `spring-framework`/`spring-webmvc` align with the Boot release in use?
- Do any `javax.servlet` artifacts or older Spring Framework artifacts enter runtime after moving to Jakarta?
- Do Maven profiles, parent POMs, properties, or reactor modules override one another?

`mvn help:effective-pom` lets you inspect the model after parents, imports, and profiles take effect. `mvn dependency:tree` gives you the **resolved dependency graph**. In multi-module projects, run and inspect the exact target module; do not infer a deployable application's tree from a secondary module.

### 4.2. Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew clean test
```

On Windows, use `gradlew.bat` or `.\gradlew.bat` depending on your shell. `runtimeClasspath`, `compileClasspath`, and `testRuntimeClasspath` can differ; `dependencyInsight` helps determine **why** Gradle picked a particular version.

In multi-project builds, specify the module path (such as `:api:dependencyInsight`) because the root project may not contain runtime dependencies. Do not rely on a single IDE library panel to claim all Gradle configurations share the same classpath.

### 4.3. Capturing evidence before making changes

A useful migration record includes:
- JDK/CI/container runtime;
- Boot parent/plugin/BOM version;
- Security resolved artifacts and versions;
- Target Servlet/container;
- Whether the app uses form login, session, Basic, Bearer, JWT, opaque tokens, OAuth2 login, or SAML;
- Unit/integration/security test results before the upgrade;
- List of explicit overrides, compatibility constraints, and known issues.

Without a baseline, when an upgrade fails it is hard to tell whether the root cause is **version alignment** or a **behavior change**.

## 5. Reading the right source and target migration documentation

Official documentation entry points:

- **Spring Boot Reference — Upgrading**: `https://docs.spring.io/spring-boot/how-to/upgrading.html`.
- **Spring Security Reference — Migration**: `https://docs.spring.io/spring-security/reference/migration/`.
- **Spring Framework documentation**: select the migration/upgrade notes matching the Framework version managed by your target Boot release.
- **Spring Boot dependency versions**: inspect the managed dependencies/BOM list of **the selected release**, rather than relying on an outdated generic version table.

These URLs are **entry points**; when reading, select the appropriate version selector, branch, or release notes. The “current” docs may describe a newer version than your project targets. Never substitute an unversioned blog snippet for a version-specific guide.

### 5.1. Choosing the guide by upgrade type

| Source → target | How to read | Notes |
| --- | --- | --- |
| Boot patch → patch | Changelog, CVEs, dependency updates, smoke tests | Do not assume “patches never change behavior” |
| Boot minor → minor | Target release notes, upgrading guide, Security minor notes | Defaults, plugins, auto-config, deprecations |
| Boot 2.x → 3.x | Boot 2→3, Security 5→6, Framework 5→6, and Jakarta | Java 17, Servlet/Jakarta packages, DSL |
| Security 5.x → 6.x without Boot | Source→target Security migration guide, Framework/Servlet compatibility | Removed APIs, request matchers, custom providers |
| Boot 3.x → newer major | Boot 3→target guide, corresponding Security/Framework target | Do **not** blindly re-apply the Boot 2→3 checklist |
| Security patch override in Boot | Boot-managed versions, supported override policy, advisory | Avoid mixing patch artifacts and release trains |

**Important:** “upgrading to Spring Security 6” only describes the major version. Different minor/patch targets of Security 6 are not identical. Pick the actual resolved target versions, then read the “breaking change/behavior change” sections for every step you cross.

### 5.2. Turning the guide into an action list

For each migration note item, record:
1. **Affected APIs/configs** (if used by the project).
2. **Code changes** required.
3. **Behavior/default changes** even when the code compiles cleanly.
4. **Related dependencies/libraries**.
5. **Regression tests** verifying before-and-after behavior.
6. **Deployment/rollback risks**.

For example, when the Security guide discusses HTTP authorization, do not just rename methods; verify that `/api/**` is still matched by the right chain, unauthorized users receive 403, anonymous requests receive 401 or the intended redirect, and CSRF is not accidentally disabled.

## 6. BOM: What does a Bill of Materials do?

A **BOM** describes a set of **managed dependency versions** for a family of artifacts or a platform. In Maven, a BOM is imported inside `<dependencyManagement>` (typically `type=pom`, `scope=import`). In Gradle, a BOM can be consumed via native `platform(...)` or the dependency-management plugin.

A BOM does **not** do the following:
- It does not automatically add dependencies to the project.
- It does not create a `SecurityFilterChain`, JWT decoder, or CSRF filter.
- It does not certify that Spring Boot + an arbitrary Security override are compatible.
- It does not guarantee the runtime classloader lacks external JARs injected by a container.
- It does not replace integration tests or code review.

Goal: **keep a group of artifacts on versions managed together**, avoiding situations where a developer pins `spring-security-core=6.5.0`, `web=6.2.0`, `config=5.8.16`.

### 6.1. Spring Boot apps: prefer Boot-managed dependencies

`spring-boot-dependencies` manages Spring Security **alongside many other libraries** (Spring Framework, JSON, embedded containers, test tooling, etc.). That is normally the default choice for a Spring Boot application.

If an application does not use Boot but uses Spring Security directly on Spring MVC/Servlet, you can import `spring-security-bom` to align Security modules. **However, the Security BOM does not manage the full Framework/Servlet ecosystem**, so compatibility must still be checked separately.

## 7. Maven: using spring-boot-starter-parent

Example Maven POM for a Spring Boot application, illustrated with Boot version `3.5.0`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-upgrade-demo</artifactId>
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

Notice that **no version is specified for the Security starter or Security Test**. The Boot parent manages compatible versions for its release. When using Resource Server, add `spring-boot-starter-oauth2-resource-server` without pinning its version separately, then configure JWT/introspection accordingly. Do not treat having the dependency as sufficient for secure authentication.

The Boot parent also provides convenient build/plugin defaults. Still, it does not automatically add every starter, authorize individual endpoints, or replace HTTPS/CSRF/session configuration.

### 7.1. Multi-module Maven and internal corporate parents

If your organization uses a corporate parent POM, a module cannot have **two** parents. You can:
- Have the corporate parent inherit from the Boot parent if policy permits; or
- Import the Spring Boot BOM in `<dependencyManagement>` of the corporate/root POM and manage build plugins separately.

Either way, child modules can still declare explicit versions or their own `dependencyManagement`. You must inspect the effective POM of every critical module.

## 8. Maven: importing spring-boot-dependencies without the Boot parent

Illustrative POM snippet:

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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This is a **POM snippet**, not a standalone runnable file. It manages dependency versions but **does not inherit all Maven plugin configurations** from `spring-boot-starter-parent`. Consequently, the project must configure `maven-compiler-plugin`, `maven-surefire-plugin`, `spring-boot-maven-plugin`, and other plugins per its own parent/build policy.

**Do not confuse the two:** `dependencyManagement` supplies version rules; `dependencies` actually requests artifacts in the graph. Importing a BOM does not declare `spring-security-config` for you, nor does it make the application accept bearer tokens without Resource Server configuration.

### 8.1. Multiple BOMs can conflict

A build importing the Boot BOM alongside another BOM may share overlapping artifact keys. Import order, direct declarations, existing `dependencyManagement`, and version overrides can all affect the selected version. Do not rely on a rule of thumb like “the last BOM always wins.” Read the **effective POM** and **resolved dependency tree**.

For Boot projects, prefer letting **a single Boot BOM source** manage the Spring stack. Only apply a Security version override when backed by advisory/compatibility evidence and tested across all runtime modules.

## 9. Maven: when to use spring-security-bom directly?

If an application uses Spring Security Servlet **without the Spring Boot BOM**, you can import the Security BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-bom</artifactId>
            <version>6.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-config</artifactId>
    </dependency>
</dependencies>
```

**Do not apply this snippet as an arbitrary override next to the Spring Boot BOM.** It illustrates a non-Boot setup. The Security BOM aligns Security modules, but it does not govern Spring Framework, Servlet container, JWT/OAuth integrations, or application server versions. System-wide compatibility still has to be verified.

Example of a **suspicious** dependency tree:

```text
org.springframework.security:spring-security-core:6.5.0
org.springframework.security:spring-security-web:6.5.0
org.springframework.security:spring-security-config:5.8.16
org.springframework.security:spring-security-test:6.5.0
```

This is synthetic data illustrating a mismatch, **not output from a real project**. Locate where `config` is pinned to `5.8.16` or where dependency resolution selects the old version, and fix it at the version-management source. Do not casually exclude `spring-security-config` if the application relies on the Security DSL.

## 10. Gradle: Boot plugin and dependency-management plugin

Example `build.gradle.kts` for a Spring Boot application using Java 17:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
```

When combining the Boot Gradle plugin and `io.spring.dependency-management` per their documentation, the Boot BOM is used to manage versions. Therefore, individual Security versions do not need to be added.

The Boot/Gradle/dependency-management plugin versions in this example are **illustrative syntax**. In real projects, verify Gradle/JDK/plugin compatibility against the target Boot release and use an approved wrapper version.

### 10.1. Gradle native platform: an alternative way to consume a BOM

If using Gradle's native BOM support, here is an example Java module using Groovy DSL:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

test {
    useJUnitPlatform()
}
```

`platform(...)` brings BOM constraints into the relevant configurations; the BOM **does not automatically add** dependencies the project has not declared. Use `dependencyInsight` to verify selected versions, especially when other constraints or forced versions exist.

You do not need to simultaneously use the dependency-management plugin, import the same Boot BOM via native `platform`, and force a different-version Security BOM. If a complex build combines multiple mechanisms, define a clear policy and inspect the actual graph.

**`enforcedPlatform`** forces versions more aggressively than `platform`; avoid using it indiscriminately in shared libraries because it exerts pressure on downstream consumers. Gradle version catalogs (`libs.versions.toml`) help manage **declared versions** but do not by themselves replace consuming a consistent BOM.

## 11. Java 17 hands-on: detecting mixed-version Security artifacts

This is a plain Java exercise using JDK 17; it demonstrates how to **check internal consistency** of Security modules after collecting resolved data from Maven/Gradle. It is **not** an official Boot/Security compatibility checker and does not parse build files.

File `SecurityVersionAuditDemo.java`:

```java
import java.util.List;

public final class SecurityVersionAuditDemo {
    record Dependency(String group, String artifact, String version) {}

    static String audit(List<Dependency> deps) {
        List<String> versions = deps.stream()
            .filter(d -> d.group().equals("org.springframework.security"))
            .map(Dependency::version)
            .distinct()
            .sorted()
            .toList();

        if (versions.isEmpty()) return "NONE";
        if (versions.size() == 1) return "ALIGNED " + versions.get(0);
        return "MIXED " + versions;
    }

    public static void main(String[] args) {
        List<Dependency> aligned = List.of(
            new Dependency("org.springframework.security", "spring-security-core", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-web", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-config", "6.5.0")
        );
        List<Dependency> mixed = List.of(
            new Dependency("org.springframework.security", "spring-security-core", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-web", "6.5.0"),
            new Dependency("org.springframework.security", "spring-security-config", "5.8.16")
        );

        System.out.println(audit(aligned));
        System.out.println(audit(mixed));
    }
}
```

Compile/run:

```bash
javac SecurityVersionAuditDemo.java
java SecurityVersionAuditDemo
```

Exact stdout:

```text
ALIGNED 6.5.0
MIXED [5.8.16, 6.5.0]
```

**Limitations:** `ALIGNED` output here only means the Security modules in the **mock list** share the same version string. It does not prove Boot, Spring Framework, and the Servlet container are compatible, nor does it check transitive dependencies, advisories, or test behavior. In real projects, the input data must come from the build tool's resolved dependency graph, not a hand-written list.

## 12. Spring Security 5 → 6 Migration: key areas on Servlet

When actually upgrading to Security major 6, read the migration guide covering API removals, defaults, and preparatory steps from the 5.x line. The items below are **areas to check**, not a mandate to change every project blindly.

### 12.1. WebSecurityConfigurerAdapter → SecurityFilterChain bean

Legacy-style configuration:

```java
// Legacy code shown for identification during migration; do not use in Security 6:
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .anyRequest().authenticated();
    }
}
```

`WebSecurityConfigurerAdapter` was deprecated in Security 5.7 and removed in Security 6. Modern pattern:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
        return http.build();
    }
}
```

This code runs **inside a Spring Boot/Spring Security application**, not standalone via `javac`. Do not just make it compile: if the old app had multiple chains, custom authentication, or route-specific config, preserve the exact semantics and order, and test filter selection.

### 12.2. authorizeHttpRequests and requestMatchers

Old config APIs like `antMatchers`/`mvcMatchers` are replaced by the appropriate matcher APIs in Security 6. For example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

**`http.securityMatcher(...)` selects the entire SecurityFilterChain**, whereas `authorizeHttpRequests(...requestMatchers...)` defines rules **after the chain has already been selected**. Spring Security typically picks the **first matching SecurityFilterChain** by order. A catch-all chain ordered before an API chain can prevent the API filters from ever running.

Do not mechanically rename `antMatchers` → `requestMatchers` and ignore semantic differences: test URLs with `contextPath`, `servletPath`, MVC mappings, encoded slashes, and your app's firewall behavior.

### 12.3. Java 17 and javax → jakarta

Spring Boot 3/Spring Framework 6 use Jakarta APIs for many Java EE namespaces. For example:

```java
// Before (for legacy Java EE APIs):
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;

// After:
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
```

Do not find-and-replace **every** `javax.`, because `javax.crypto`, `javax.net.ssl`, and many Java SE packages remain unchanged. Only migrate the relevant Jakarta EE packages and upgrade Servlet container/Validation/JPA library dependencies per the guide. A Jakarta WAR will not run as-is on an older Java EE servlet container.

Spring Boot 3 requires Java 17 or newer; you must also upgrade your **CI JDK, toolchain, Docker runtime, and compiler plugin** to the target version, not just `java.version` in the POM.

### 12.4. Method security

If the application uses `@EnableGlobalMethodSecurity`, read the guide for `@EnableMethodSecurity` and differences in `AuthorizationManager`, defaults, and expression evaluation.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
```

`@PreAuthorize`/`@PostAuthorize` must also be tested with both authorized and unauthorized users. Calling a method directly via `this.method()` bypasses the Spring proxy; upgrading the annotation will not fix broken proxy architecture.

### 12.5. SecurityContext and saving the context

In Security 6 Servlet, `SecurityContextHolderFilter` and `SecurityContextRepository`/explicit saving can affect custom authentication. If you create an `Authentication` after login that **must persist across subsequent requests**, consult the guide and consider:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// Only for stateful flows that need to persist the context for subsequent requests:
securityContextRepository.saveContext(context, request, response);
```

This is a **snippet inside a handler where `authenticated`, `request`, `response`, and `repository` already exist**, not a standalone file. Do not “fix” issues by persisting every Bearer `Authentication` into the HTTP session: a stateless Resource Server has a different threat model.

### 12.6. Changes that do not cause compile errors

In particular, verify:
- Does anonymous `GET /api/**` return 401 or a 302 redirect?
- Do cookie-authenticated `POST` requests still have CSRF protection?
- Does session fixation rotate the session ID after login?
- Do logout, remember-me, and concurrent sessions still behave accurately?
- Does the Resource Server still verify JWT signature, issuer, audience, and expiry?
- Does access denied return 403 when lacking scope/authority?
- Do static assets and public endpoints receive headers as designed?
- Is any custom filter added to the right chain/order without double registration?
- Do error/async dispatches cross the required security boundary?

**A BOM cannot detect these behavioral bugs.**

## 13. Spring Security 6 example: two chains with testable behavior

File `TwoChainsConfig.java` in a Spring Boot Servlet app:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TwoChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

The API chain precedes the web catch-all chain. `securityMatcher` selects the chain; `requestMatchers` inside `authorizeHttpRequests` selects rules. The example does not disable CSRF globally: browsers can automatically send HTTP Basic credentials or cookies, so CSRF must be evaluated based on the credential mechanism. If a real API uses Bearer headers only, design the Resource Server + CSRF policy per its trust model; do not copy `csrf.disable()` arbitrarily.

File `SmokeController.java`:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SmokeController {
    @GetMapping("/api/public/ping")
    String ping() { return "pong"; }

    @GetMapping("/api/private")
    String privateApi() { return "private"; }

    @GetMapping("/dashboard")
    String dashboard() { return "dashboard"; }
}
```

These endpoints serve only as security chain regression tests and carry no business data. If testing successful Basic login, provide a matching `UserDetailsService`/test credentials; the anonymous tests below require no specific user assumptions.

## 14. MockMvc security regression tests after an upgrade

File `SecurityUpgradeSmokeTests.java` in a project with `spring-boot-starter-test` and `spring-security-test`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityUpgradeSmokeTests {
    @Autowired MockMvc mvc;

    @Test
    void anonymousApiGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void publicApiIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void similarPrefixIsNotApiChain() throws Exception {
        mvc.perform(get("/apiary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Run:

```bash
mvn -Dtest=SecurityUpgradeSmokeTests test
# Or with a Gradle project that has the test task configured:
./gradlew test --tests SecurityUpgradeSmokeTests
```

This is a **minimum smoke** suite. There is no fixed application stdout because the test runner controls reporting. It proves a few boundaries between API and web chains; it does not by itself prove JWT cryptographic verification, CSRF on POST, sessions, or method authorization.

### 14.1. Test matrix needed beyond smoke tests

| Area | Negative/positive tests |
| --- | --- |
| Login/session | Wrong/valid password; session fixation ID rotation; concurrent sessions if enabled |
| CSRF | Unsafe POST without token blocked under cookie auth; POST with valid token allowed if authorized |
| HTTP Basic | Missing header / bad header / valid credentials; entry point does not redirect improperly |
| JWT Resource Server | Invalid signature, expired, wrong issuer/audience; valid/missing scope |
| OAuth2 Login | Authorization redirect, callback, state, user mapping, logout |
| Method security | `@PreAuthorize` with authorized/unauthorized role and owner |
| URL matchers | `/api/**`, `/apiary`, `contextPath`/`servletPath`, encoded path variants |
| HTTP headers | CSP, nosniff, HSTS over HTTPS, session cookie flags |
| Session/remember-me | Logout/invalidated session, remember-me token lifecycle |
| Error/async | Error dispatch, async worker/auth context, custom filters |
| Persistence/Jakarta | Controllers, validation, JPA, Servlet filters compile and run properly |

**When using `with(jwt())` in Spring Security Test**, that is a mock authentication, **not proof that your JWT decoder verified a real token signature**. Write corresponding integration tests when Resource Server is a critical component.

## 15. Distinguishing version/classpath errors from security behavior bugs

| Symptom | Check first |
| --- | --- |
| `NoSuchMethodError` | Are two versions of Framework/Security/Jakarta on the runtime classpath? |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing artifact, wrong scope, or WAR/container classpath differs from IDE? |
| Build compiles but app fails to start | Boot auto-config, Servlet container, plugin/Java baseline, version graph |
| API returns 302 to login instead of 401 | `SecurityFilterChain` match/order, authentication entry point |
| 403 after upgrade | CSRF filter or `AuthorizationFilter`/method security? |
| Anonymous request gets 200 on protected endpoint | Chain didn't match, wrong bypass/`permitAll`, method security ineffective |
| Valid JWT gets 401 | Decoder/issuer/audience/clock/algorithm, filter in the right chain? |
| `spring-security-test` throws runtime errors | Is the test module version aligned with runtime Security/Framework? |
| Static assets lose security headers | `web.ignoring`, matcher, filter chain, proxy/CDN rewrite? |
| App upgraded to Boot 3 runs on old server | Servlet/Jakarta container incompatibility? |

If the classpath is not right yet, **fix dependency alignment first** so subsequent errors are meaningful. Once the classpath is clean and requests still fail, analyze security behavior using safe logs, chain inventory, and tests. Do not “fix” it by loosening `permitAll` or disabling CSRF for convenience.

## 16. Rollout and rollback after an upgrade

For a production application, an upgrade should proceed in stages:

1. **Baseline:** capture dependency trees, test results, Java/container versions, security config, and HTTP contracts.
2. **Select target:** verify supported releases/lifecycles, BOM/managed versions, and compatibility matrix.
3. **Read source→target guides:** Boot + Security + Framework/Jakarta + integrations; maintain a migration ledger.
4. **Align build:** update versions at the right parent/BOM/plugin; remove unnecessary overrides; test multi-module builds.
5. **Migrate source:** update APIs, imports, filter-chain selection, method security, and custom auth lifecycles.
6. **Test:** compile, full test suite, MockMvc, HTTP integration, browser/session, OAuth/JWT, deployment smoke.
7. **Staging:** run on real JDK/container, inspect logs/headers/metrics, verify cookies/sessions.
8. **Rollout:** canary or progressive rollout; monitor 401/403/5xx, login failures, latency, token validation.
9. **Rollback:** retain previous artifacts/container images and configuration; assess whether schema/session/serialization migrations are rollback-compatible.
10. **Document:** record the source/target pair, before/after dependency trees, guides referenced, test evidence, and items to watch.

**Warning:** do not leave broad `org.springframework.security=TRACE` logging enabled for long in production; logs can expose URLs, sessions, principals, or raw credentials logged by custom filters. Never put bearer tokens, cookies, or passwords into CI artifacts.

## 17. Common mistakes

1. **Searching for “Spring Security latest” and pinning it in a Boot app** instead of checking the Boot BOM.
2. **Adding a BOM under `dependencies` as a runtime JAR** instead of `dependencyManagement`/`platform`.
3. **Assuming all modules are aligned because starters omit versions** while another module overrides `spring-security-web`.
4. **Reading a migration guide for a major version you are not crossing**, leading to unnecessary or wrong code edits.
5. **Upgrading only `spring-security-config`** while ignoring `core`, `web`, `test`, and Framework.
6. **Running a global `javax` → `jakarta` find-and-replace** and inadvertently breaking unchanged Java SE packages.
7. **Stopping once it compiles** without testing filter chains, 401/403, CSRF, authorization, and sessions.
8. **Confusing `securityMatcher` with `authorizeHttpRequests().requestMatchers`**, routing endpoints into the wrong chain.
9. **Placing a catch-all chain before an API chain**, preventing API authentication filters from being selected.
10. **Ignoring the actual runtime container/JDK**: building on a newer JDK while deploying to an older JVM or incompatible servlet container.
11. **Importing multiple BOMs or overlapping version constraints** without inspecting `dependencyInsight`/effective POM.
12. **Using `enforcedPlatform` to force the entire dependency graph** before understanding the conflict cause.
13. **Mixing up test classpath and runtime**: `spring-security-test` may differ in release line or CI profiles may differ from local.
14. **Disabling CSRF or widening `permitAll` to make tests green**, masking real security regressions.
15. **Assuming one 200 smoke test proves the migration safe**; negative tests and full auth flows are required.
16. **Failing to prepare rollback**, especially when session state, token persistence, or DB schemas change.

## 18. Self-acceptance checklist

- [ ] A source/target table exists for **Java, Boot, Security, Framework, Servlet**, and integrations.
- [ ] **Exact** Boot/Security/Framework migration guides have been read for every upgrade step.
- [ ] Boot app uses Boot parent/BOM/plugin as the primary version-management source.
- [ ] Individual Spring Security modules are not pinned without justification and support evidence.
- [ ] Maven effective POM or Gradle `dependencyInsight` confirms resolved versions.
- [ ] `spring-security-test` matches the runtime release line.
- [ ] Java toolchain, CI image, and Servlet container/Jakarta dependencies are compatible.
- [ ] `SecurityFilterChain` beans have accurate matchers/order; no sensitive endpoints fall outside a chain.
- [ ] Method security, authentication providers, custom filters, logout, and session lifecycle are re-tested.
- [ ] CSRF remains properly protected according to how browsers send credentials.
- [ ] JWT/OAuth login/Resource Server tests verify real semantics, not just mocked `Authentication`.
- [ ] Negative tests cover 401, 403, sessions, invalid tokens, and sensitive URL patterns.
- [ ] Application has run on production-like staging with security logs/metrics safely observed.
- [ ] Canary/rollback plan exists, especially for migrations that are hard to revert.
- [ ] PR/issue records the version pair, before/after dependency graph, and QA results.

**Conclusion:** In Spring Security Servlet, a proper upgrade is a **version-pair controlled process**, not swapping dependencies at random. Read the **exact source→target migration guide**, prefer the **Spring Boot BOM** when using Boot, inspect the dependency tree/`dependencyInsight` to confirm the classpath, and then prove via **HTTP security regression tests** that chains, login, sessions, CSRF, JWT/OAuth, and authorization have not changed unintentionally. A BOM solves version alignment; **it does not replace code migration or security testing**.
