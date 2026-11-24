# Choosing Spring Boot, Spring Security, and Compatible Dependency Versions

> Scope: **bootstrapping a Spring Security application on WebFlux (reactive)**. Version examples are cross-checked against official documentation as of **2026-11-07**. Patch releases may change after this date; when starting a new project or upgrading, consult the current list of supported versions.

## 1. Why must versions be chosen as a set?

A secure reactive application is not just two independent libraries. It is a stack of layers that must be compatible with each other:

~~~text
Java (JDK/JVM running the application)
       |
Maven/Gradle + Spring Boot parent/BOM
       |
       +-- Spring Boot: auto-configuration, starters, packaging, running the app
       +-- Spring Framework: Spring WebFlux, web/reactive APIs
       +-- Spring Security: reactive authentication, authorization
       +-- Reactor / Reactor Netty: Mono, Flux, asynchronous HTTP server
       +-- Related libraries: test, codec, JWT/OAuth2, database driver...
~~~

Essential concepts:

- **Spring Boot** manages how the application is bootstrapped, configured, and packaged, and provides a list of dependencies tested together.
- **Spring Framework** provides WebFlux; each Spring Boot line is tied to a compatible Spring Framework line.
- **Spring Security** provides reactive APIs such as `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveSecurityContextHolder`. Spring Security also has Servlet/MVC APIs; you must choose the right stack.
- **Reactor** is the underlying Publisher library for `Mono` and `Flux`; WebFlux and reactive Security both operate on this mechanism.
- **BOM (Bill of Materials)** is a mapping table from groups/libraries to versions. `spring-boot-dependencies` manages most Spring libraries and many third-party libraries.

**Default principle:** first choose **a stable Spring Boot version**, then let `spring-boot-starter-parent` or the Spring Boot BOM determine the versions of Spring Framework, Spring Security, Reactor, and the dependencies within its managed scope. Do not manually mix and match the latest versions of individual libraries as independent pieces.

## 2. Illustrative version matrix as of 2026-11-07

| Consistent version set | Spring Boot | Spring Framework managed by Boot | Spring Security managed by Boot | Minimum Java | When to consider |
| --- | --- | --- | --- | --- | --- |
| New branch | **4.1.2** | **7.0.10** | **7.1.2** | **17** | New projects that can adopt Spring Framework 7, Security 7, and the corresponding ecosystem |
| 3.x branch | **3.5.16** | **6.2.19** | **6.5.11** | **17** | Projects staying on Boot 3.x or with dependencies not yet compatible with Boot 4 |

These numbers come from the `System Requirements` and `Managed Dependency Coordinates` documentation for each Spring Boot line, not from a guess that "the same major number is enough". In particular, **do not assume Boot 4.1.2 must use Spring Security 4.1.2**. Spring Boot 4.1.2 manages Spring Security **7.1.2**.

Additional notes:

- Boot **4.1.2** documentation specifies build support with Maven **3.6.3+** or Gradle **8.14+ on the 8.x branch / 9.x branch**; minimum Java 17. Choose an LTS JDK suitable for your system and check the CI/production JVM version, not just your local machine.
- Boot **3.5.16** documentation specifies Maven **3.6.3+**, Gradle **7.6.4+ on the 7.x branch / 8.4+ on the 8.x branch**; minimum Java 17. Do not assume an overly old Gradle wrapper will still work after changing the Boot major version.
- The **4.0.x** branch also belongs to the Spring Framework 7 / Security 7 generation; treat it as an option requiring separate evaluation, do not simply swap version numbers in a 3.x project while skipping migration.
- "Stable" does not mean "supported forever". Check Spring's support policy and security advisories before locking a version for a long-lived application.
- Do not choose `M` (milestone), `RC` (release candidate), or `SNAPSHOT` releases for regular production unless you have accepted the risk and have a dedicated testing process.

**Decision rule:** if starting a new reactive service and all related libraries support Boot 4.1, use the current 4.1.x set; if operating on Boot 3.5 with dependencies not yet ready for Framework 7 or Security 7, continue using the appropriate latest patch of the 3.5 line while preparing for migration. Do not force a major upgrade just to have a higher version number.

## 3. Repeatable version selection workflow

### Step 1 — Record real-world constraints

Answer these questions before choosing a version:

1. Does the application run on **Java 17, 21, 25, or another runtime**? Do the build JDK and production JVM match?
2. Is the project **pure WebFlux reactive** or **Spring MVC/Servlet**? If both MVC and WebFlux starters are present, you must verify which stack Boot actually activates.
3. Which security features are needed: session, HTTP Basic, JWT resource server, OAuth2 client/OIDC, SAML, method security?
4. Are there dependencies on Spring Cloud, Spring Data, database drivers, Spring Authorization Server, or third-party libraries that do not yet support the new Boot/Security major?
5. Are there support lifecycle requirements, security patches, container/native image deployment formats, or mandatory Gradle/Maven versions?

A single unmet constraint can make the entire chosen set unsuitable, even if `spring-boot-starter-security` alone can still be downloaded from Maven Central.

### Step 2 — Verify the Spring Boot line

Read the `System Requirements` for the exact branch, checking Java, Maven/Gradle, Spring Framework, and support information. Do not use the `latest` page to draw conclusions about constraints for a project pinned to 3.5.x.

### Step 3 — Look up the BOM for actual versions

Open `Managed Dependency Coordinates` for the **exact Boot version**. Look up `spring-security-core`, `spring-security-web`, `spring-webflux`, `reactor-core`, and any other modules the project uses. If a library is in the BOM, **declare the dependency without `<version>`** (Maven) or use the platform/dependency management mechanism (Gradle).

### Step 4 — Check the extended ecosystem

For example, if using Spring Cloud Gateway, Spring Cloud Config, or Spring Cloud Stream, you must find the **Spring Cloud release train published as compatible with the selected Boot branch**. The Spring Boot BOM does not automatically verify compatibility for every third-party starter. Do the same for R2DBC drivers, test tools, build plugins, and integrated OAuth2/JWT libraries.

### Step 5 — Run the build and security tests

Inspect the resolved dependency tree, run compile/test, start the web server, and test at least a request without credentials, valid credentials, and an insufficient-permissions case. **Maven being able to download a JAR does not prove API compatibility at runtime**.

## 4. Which dependencies to choose for reactive Spring Security?

For a WebFlux HTTP application, the two required starters are usually:

| Need | Suitable Spring Boot starter | Reason |
| --- | --- | --- |
| Reactive HTTP server | `org.springframework.boot:spring-boot-starter-webflux` | WebFlux, Reactor, and Reactor Netty by default |
| Authentication/authorization | `org.springframework.boot:spring-boot-starter-security` | Spring Security and Boot's security configuration |
| WebFlux testing on Boot 4.1 | `org.springframework.boot:spring-boot-starter-webflux-test` (`test` scope) | WebFlux test infrastructure |
| Security testing on Boot 4.1 | `org.springframework.boot:spring-boot-starter-security-test` (`test` scope) | Security testing utilities |
| JWT/OAuth2 resource server on Boot 4 | `org.springframework.boot:spring-boot-starter-security-oauth2-resource-server` | Validates access tokens according to resource server configuration |
| Outbound reactive HTTP calls on Boot 4 | `org.springframework.boot:spring-boot-starter-webclient` | `WebClient` API, when the application needs an HTTP client separately |

Only add optional starters if there is a real need. A single `spring-boot-starter-webflux` typically already pulls in `spring-webflux`, Reactor, and Reactor Netty; there is no need to add `reactor-core` or `spring-security-web` with a manual version just to make an example work.

**Test branch difference:** on Boot **3.5**, the common setup is `spring-boot-starter-test` and `org.springframework.security:spring-security-test`, both with `test` scope. Boot **4.x** organizes starters into more granular modules, including the corresponding `*-test` starters. When moving from 3.5 to 4.x, check starter names and test package paths rather than just changing numbers in the build file.

**Be careful when adding a web stack:** `spring-boot-starter-web` (Boot 3.x) or `spring-boot-starter-webmvc` (Boot 4.x) is Servlet MVC. For reactive WebFlux labs, only add it when intentionally designing a combined setup and after understanding the web application type selection rules; do not include it by copying dependencies from an MVC sample.

## 5. Maven: runnable Boot 4.1.2 project example

Use [Spring Initializr](https://start.spring.io/) with Maven, Java 17+, group `com.example`, artifact `reactive-versions`, and select **Spring Reactive Web** and **Spring Security**. The following minimal complete `pom.xml` illustrates how to let the Boot parent manage versions:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-versions</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactive-versions</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
~~~

Notice that **only the parent has version 4.1.2**; the four starters have no `<version>` tag. The Boot parent provides dependency management and manages many related Maven plugins. When upgrading Boot 4.1.x to the next patch release, you typically update `<parent><version>...` and re-run QA instead of changing each child dependency.

Create the file `src/main/java/com/example/reactiveversions/ReactiveVersionsApplication.java`:

~~~java
package com.example.reactiveversions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveVersionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveVersionsApplication.class, args);
    }

    @RestController
    static class PingController {
        @GetMapping("/ping")
        public Mono<String> ping() {
            return Mono.just("pong");
        }
    }
}
~~~

This is a **complete Java class** for the directory structure and `package` above, without needing to add Security code yourself to enable the default policy. Spring Boot automatically configures protection for WebFlux endpoints when `spring-boot-starter-security` is present; the default configuration is meant for development and must be replaced with your application's policy before going to production.

In the directory containing `pom.xml`, if you have the Maven wrapper generated by Spring Initializr:

~~~bash
./mvnw clean verify
./mvnw spring-boot:run
~~~

On Windows use `.\mvnw.cmd clean verify` and `.\mvnw.cmd spring-boot:run`. Run the following command in another terminal:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/ping
~~~

**Expected result:** HTTP **401 Unauthorized** when no credentials are sent. The default configuration has user `user` and a random password logged by Spring Boot in the startup log in development environments. Use the generated password to retry and receive body `pong`; do not commit this password into the repository and do not use the default mechanism for production. The headers and body content of the 401 response may vary by version/configuration.

The example demonstrates that **the build dependencies and default web security work together**; it is not yet a production authentication/authorization configuration, and it does not verify every OAuth2 option or database driver.

## 6. If using Gradle Kotlin DSL

When not using Maven, keep the Boot plugin and Gradle BOM on the same 4.1.2 line. Here is a `build.gradle.kts` example using **Gradle native platform** instead of the dependency-management plugin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Keep the same `ReactiveVersionsApplication.java` file from the Maven section. Use a Gradle wrapper generated with a version supported by Boot 4.1:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

Windows: `.\gradlew.bat clean test` and `.\gradlew.bat bootRun`. A minimal `settings.gradle.kts` file can set the name using `rootProject.name = "reactive-versions"`.

**Gradle BOM explanation:** the `org.springframework.boot` plugin creates run/package tasks on its own, but **that does not mean every dependency's version is automatically managed without importing the BOM**. Here `platform(SpringBootPlugin.BOM_COORDINATES)` imports the version set of that exact Boot plugin. Besides this approach, you can use the `io.spring.dependency-management` plugin; choose **one consistent approach** and inspect the resolution result, avoiding duplicate BOMs or arbitrary overrides.

Gradle `platform` provides **recommended version constraints**. Another dependency or constraint in the graph can still cause a different version to be selected. Therefore `dependencyInsight` is an important verification step, especially when integrating libraries outside the BOM.

## 7. When staying on Spring Boot 3.5.x

If the application currently uses Boot 3.5, Spring Framework 6.2, and Spring Security 6.5, adding reactive security is equally straightforward: use `spring-boot-starter-webflux` and `spring-boot-starter-security` while **letting the Boot 3.5 BOM manage the corresponding 6.x versions**.

The Maven snippet differs in the parent version and test configuration:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<!-- Application dependencies: spring-boot-starter-webflux,
     spring-boot-starter-security, without declaring separate versions. -->
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
~~~

**This is only a configuration snippet to compare inside an existing `pom.xml`**, not a standalone POM file; for a 3.5 project, keep the existing `groupId`, `artifactId`, `properties`, `build`, and application dependencies.

Do not do the following:

~~~xml
<!-- Example NOT to use: Boot 3.5 manually paired with Security 7 -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.1.2</version>
</dependency>
~~~

This is an example of **an incorrect configuration to recognize**, not to copy into a build. Boot 3.5 manages Spring Framework 6.2 / Security 6.5, whereas Security 7 belongs to the generation integrating with Spring Framework 7. Mixing majors can cause build failures, `NoSuchMethodError`, or `ClassNotFoundException` at runtime. To upgrade to Security 7, plan an upgrade of **the entire Boot line** and related libraries following the migration guides.

## 8. When you must use the BOM without inheriting the Spring Boot parent

In a multi-module Maven project with a custom parent, you can **import** the Boot BOM inside `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Afterwards, starters do not need to declare versions if they belong to the BOM. **Important difference:** importing the BOM manages **dependency versions**; it does not replace all the **plugin management**, resource filtering, compiler, and packaging configuration from `spring-boot-starter-parent`. With a custom parent, you need to configure the appropriate build/Java release plugins, including required plugin versions.

If you add another BOM (for example Spring Cloud), read the corresponding release train documentation and dependency-management precedence rules; do not assume the order of BOM declarations or dependency order is always harmless.

## 9. Verifying resolved versions — the source of truth is the dependency graph

### Maven

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

These commands sequentially verify Maven/JDK, the POM configuration after inheritance, the resolved dependency graph, and the build/test outcome. On Windows replace `./mvnw` with `.\mvnw.cmd`.

Look in `dependency:tree` for the actual modules such as `spring-boot`, `spring-webflux`, `spring-security-core`, `spring-security-web`, `reactor-core`, and `reactor-netty-http`. With a Boot 4.1.2 configuration without overrides, you expect the BOM-managed modules to match the set **Spring Framework 7.0.10**, **Security 7.1.2**; Boot 3.5.16 corresponds to **Framework 6.2.19**, **Security 6.5.11**. Always inspect the actual output rather than assuming every dependency in the graph shares the same version.

### Gradle

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew clean test
~~~

On Windows replace `./gradlew` with `.\gradlew.bat`. `dependencyInsight` shows the selected version and why Gradle resolved that version, which is very useful when a direct dependency or constraint pulls in another version.

### How to quickly interpret results

| Observation | Interpretation | Action |
| --- | --- | --- |
| Boot 4.1.2 + Security 7.1.2 + Framework 7.0.10 | Matches the looked-up BOM set | Run tests and verify features |
| Boot 3.5.16 + Security 6.5.11 + Framework 6.2.19 | Matches the 3.5 BOM set | Maintain patches and migration plan |
| Both Security 6.x and 7.x appear | A library or override may be pulling in the wrong major | Find the dependency branch causing the conflict |
| `NoSuchMethodError`, `NoClassDefFoundError` | Possible API/binary incompatibility, skewed classpath | Inspect dependency tree and stack trace |
| `UnsupportedClassVersionError` | Bytecode was compiled for a newer Java than runtime | Check `java -version` and toolchain/release |
| `javax.*` / `jakarta.*` errors on major upgrade | Legacy APIs may remain in libraries or source code | Check migration guide and dependencies |
| Build succeeds but requests do not pass through reactive filter | May have misconfigured Servlet stack or missing reactive security chain | Check starters, web type, and SecurityWebFilterChain |

Do not "fix" compatibility errors by stuffing an arbitrary JAR in just to silence `ClassNotFoundException`; first identify a consistent dependency set and the root cause of the conflict.

## 10. When should you override Security or Reactor versions?

Normally **no override is needed**. Some justified cases are an urgent security patch or needing a fix released before the corresponding Boot patch. In those cases:

1. Identify the advisory/CVE and the versions actually affected.
2. Prefer updating to a **Spring Boot patch** that already manages the fix.
3. If none is available yet, read the official Spring Security documentation and compatibility matrix with Spring Framework. Override within **the same compatible branch**, do not manually bump the Security major version.
4. Keep Spring Security modules consistent, inspect the entire dependency graph; test authentication, authorization, CSRF, and OAuth2/JWT if used.
5. Document the reason, scope, and expiration of the override so you can return to the BOM once Boot releases the appropriate patch.

With Maven inheriting the Boot parent, Spring Security may provide the `spring-security.version` property for overrides per official documentation. With Gradle native platform, the override mechanism is not like a Maven property: use controlled resolution strategies/constraints and re-check `dependencyInsight`. **Do not write different versions of `spring-security-*` on individual dependencies**.

Similarly, do not manually swap in the latest Reactor Netty/Reactor Core without verifying against the current Spring Framework/WebFlux and Boot. Passing unit tests does not rule out protocol or event-loop compatibility errors at runtime.

## 11. Common pitfalls

**Pitfall A — writing versions on every starter and module.**

~~~xml
<!-- Do not follow -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <version>4.1.2</version>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>6.5.11</version>
</dependency>
~~~

With Boot 4.1.2, forcing Security 6.5.11 mixes incompatible generations. The right way: use the Boot parent/BOM and declare starters **without versions**; only add modules directly when the application actually uses that API.

**Pitfall B — assuming Security and Boot share the same major version.** Their versioning differs: Boot 4.1.2 corresponds to Security 7.1.2 per the BOM at the time of this lesson.

**Pitfall C — forgetting the runtime environment's Java.** `java.version` or Gradle toolchain does not automatically update the JVM inside containers, CI, or deployment hosts. Check both build and runtime.

**Pitfall D — copying Servlet configuration.** Reactive uses `SecurityWebFilterChain` and `ServerHttpSecurity`, which differ from `SecurityFilterChain` and `HttpSecurity` in MVC/Servlet.

**Pitfall E — treating the Boot Gradle plugin as automatically importing the BOM.** With Gradle you must actually configure dependency management/plugin or `platform`; always inspect the graph.

**Pitfall F — ignoring libraries outside the BOM.** Spring Cloud starters, custom OAuth2, drivers, or logging libraries may require a specific branch. Check compatibility docs and run integration tests.

**Pitfall G — unknowingly using `RC`/`SNAPSHOT` releases.** Preview releases are suitable for experimentation, not the default choice when releasing a new service.

## 12. Hands-on exercises

1. Create a Boot **4.1.2** Maven project with `starter-webflux` and `starter-security` as in Section 5, Java 17+.
2. Inspect `effective-pom` and `dependency:tree`. Record the **actual resolved versions** of Boot, Framework, Security, and Reactor resolved by Maven.
3. Run `ReactiveVersionsApplication`. Try `GET /ping` without logging in and explain the 401 result.
4. In a practice copy of the project, switch to Boot **3.5.16** while updating the corresponding test starters; do not manually write versions on individual Spring modules. Re-run the build and compare the dependency tree.
5. State why "Boot 3.5.16 + Security 7.1.2" is not an appropriate default choice.

**Key takeaway:** the BOM of the right Spring Boot release is the starting point for a consistent set of libraries. A reactive stack needs WebFlux and reactive security APIs; choose Java/Gradle/Maven within the supported range; verify the dependency graph, build, runtime, and security behavior before finalizing deployment.

## 13. Official documentation

- [Spring Boot — System Requirements, current branch](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot — Spring Security, WebFlux Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html)
- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
