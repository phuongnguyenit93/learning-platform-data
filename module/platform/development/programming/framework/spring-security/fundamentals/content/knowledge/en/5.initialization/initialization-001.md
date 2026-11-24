# Choosing a Compatible Version Set Across Java, Spring Boot, and Spring Security

When starting a Spring Security project, the first question is usually: "Which Java version, which Spring Boot version, and which Spring Security version should we use?" These three numbers are **not chosen independently**. An application can use a very new JDK and still fail to start because Spring Boot does not support that version; it can also compile successfully yet fail with `NoSuchMethodError` because multiple different Spring versions were accidentally mixed.

The goal of this lesson is to know how to **choose a verified version set**, create a runnable project, read the dependency tree, and know when an upgrade is needed. The most important mindset: **choose a suitable Spring Boot version, let Spring Boot manage the Spring Framework and Spring Security versions, and then pick a JDK and build tool within the range supported by Boot**.

Specific version details are cross-checked against the official documentation as of **November 4, 2026**. Patch versions and support status will change over time, so the verification process below matters more than memorizing a single number.

## 1. Three Version Layers Have Different Roles

| Component | What does it determine? | Where do you choose it directly? |
| --- | --- | --- |
| **Java/JDK** | Language, compiler, JVM running the application, and bytecode compatibility | Install the JDK, configure the Java toolchain and `java.version` or `maven.compiler.release` |
| **Spring Boot** | Application foundation, auto-configuration, starters, packaging plugins, dependency management/BOM | `spring-boot-starter-parent` or the Spring Boot plugin/BOM version |
| **Spring Security** | Authentication, authorization, security filter chain, OAuth2, request protection library... | Usually **no separate version is declared** when using a Boot-managed starter |

There is also an important middle layer, **Spring Framework**: Boot targets a suitable Framework range; Spring Security also depends on Framework modules. Normally you do not need to choose the Framework version yourself if you are using Boot properly.

A valid combination must satisfy **all of the following simultaneously**:

~~~text
JDK used to build/run is supported by Boot
          AND
Spring Framework is compatible with Boot
          AND
Spring Security is compatible with Framework and Boot
          AND
Build tool/plugins are suitable
          AND
Additional libraries (if any) do not break the dependency set
~~~

Do not check only `java -version` and treat that as proof that the entire system is compatible.

## 2. Two Published Reference Sets

According to official documentation checked on November 4, 2026:

| Item | Spring Boot 3.5 Set | Spring Boot 4.1 Set |
| --- | --- | --- |
| Reference Spring Boot | **3.5.16** | **4.1.2** |
| Spring Security managed by Boot BOM | **6.5.11** | **7.1.2** |
| Spring Framework | **6.2** line, requires at least **6.2.19** | **7.0** line, requires at least **7.0.10** |
| Minimum Java | **17** | **17** |
| Java stated in Boot docs as compatible up to | **25** | **27** |
| Maven | **3.6.3+** | **3.6.3+** |
| Gradle stated as supported | **7.6.4+ in the 7.x line** or **8.4+ in the 8.x line** | **8.14+ in the 8.x line** or **9.x** |
| Web MVC starter used in examples | `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| Basic security starter | `spring-boot-starter-security` | `spring-boot-starter-security` |

These are **two sample combinations grounded in the BOM and System Requirements**, not a table claiming every 3.x/4.x version is automatically compatible with every 6.x/7.x version. A Boot patch release can change the Security version it manages; to know for sure, read the **Managed Dependency Coordinates** for the **exact Boot version you plan to use**.

Sources for the table:

- Spring Boot 4.1 — [System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) and [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html).
- Spring Boot 3.5 — [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html) and [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
- Spring Security — [Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html).

**The latest version is not automatically right for every system.** If an existing project runs reliably on Boot 3.5 and depends on a library that only supports Framework 6, do not arbitrarily upgrade Security to 7. Conversely, a new project wanting to use Boot 4 needs to check its starters, Java/Jakarta, plugins, and other libraries.

### Stable, Preview, and Snapshot Are Different

As of the reference date, Boot **4.2.0-RC1** and Security **7.2.0-RC1** are *release candidates*, not the stable releases chosen for the examples. `SNAPSHOT` builds change frequently. For hands-on practice, CI, or production, choose a **released stable version**, then apply tested patch updates.

The notation `4.1.2` consists of major/minor/patch. Bumping a patch version is usually safer than changing a major version, yet you still need to run tests and check release notes, especially for security libraries with CVE fixes.

## 3. Decision Process from Scratch

### Step 1 — Identify Project Constraints

Answer these questions first:

1. Is this a **new** project or an **actively maintained existing** system?
2. Which JDK can production run? JDK 17, 21, or 25? Is a specific version mandated by the deployment environment?
3. Does the application use **Spring MVC/Servlet** or **WebFlux/Reactive**?
4. Does it depend on Spring Cloud, Spring Data, third-party Spring libraries, an external application server, Jakarta APIs, or GraalVM?
5. Which Maven/Gradle versions can CI, the Docker image, and the actual host use?
6. Does the chosen version still receive updates and security patches as required by the project?

When there are no special constraints and you are starting a new project, Java **21 LTS** is a practical choice for learning: modern enough for many Java features and supported by both reference sets above. Java 17 remains the minimum published by both of these Boot lines; Java 25 can also fit once infrastructure and other libraries have been tested. There is no reason to run Java 27 just because Boot 4.1 lists compatibility up to that version.

### Step 2 — Choose a Stable Spring Boot Line

- **New projects where libraries already support the Spring Framework 7 ecosystem:** you can choose Boot 4.1.2.
- **Projects that need to stay on Spring Framework 6 usage and corresponding dependencies:** you can choose Boot 3.5.16, while checking support timelines, patches, and an upgrade plan.
- **Legacy systems on Java 8 or 11:** cannot upgrade as-is to either reference set above, because both require Java 17 or higher. Plan a JDK upgrade and code/library updates first.
- **Using Spring Cloud:** you must select a Cloud release train compatible with the Boot line in use, according to the official Spring Cloud compatibility matrix. Boot's BOM does not replace this step.

Do not pick the highest Security release on Maven Central first and then try to force Boot to match it. With Boot, start from a clear **platform/BOM**.

### Step 3 — Check System Requirements for the Exact Line

Check the **minimum/maximum tested Java**, Maven/Gradle, Spring Framework, and secondary limits. For example, Boot 4.1.2 requires Java 17+ and states compatibility up to Java 27, yet Gradle must be 8.14+ in the 8.x line or the 9.x line. An older Gradle 8.5 **does not meet** the build requirements of Boot 4.1.2, even if the JDK is already 21.

"It runs on one machine" is not enough to conclude that a **combination is supported**. Java version, operating system, framework, JVM flags, container, and plugins all affect the outcome.

### Step 4 — Check the Boot BOM and Keep the Managed Security Version

Spring Boot provides a Bill of Materials (`spring-boot-dependencies`) listing curated versions. Boot starters (including `spring-boot-starter-security`) receive their versions from the **parent/BOM**. If you use the dependency management mechanism properly, you do not need to write `<version>` for Spring Security modules.

For example:

~~~text
Spring Boot 4.1.2
  -> Boot 4.1.2 BOM
      -> Spring Security 7.1.2
      -> corresponding Spring Framework 7.0.x
      -> other supporting libraries in the managed set
~~~

This is a version relationship, not a runtime call diagram. The Boot BOM aligns modules; it does not by itself prove that every external dependency is compatible.

### Step 5 — Generate the Project, Build, and Run Tests

Start from [Spring Initializr](https://start.spring.io/) or a POM/Gradle build with an explicit platform. Build and run using the **actual JDK of CI/production**, not just the IDE's JDK. Inspect the dependency graph to see which Security and Framework versions actually resolve, then smoke-test a secured endpoint.

## 4. Complete Maven Example: Java 21 + Boot 4.1.2 + BOM-Managed Security

This is a minimal servlet project. The sole purpose of this source code is to prove that **the chosen dependency set can build and start**, and that an endpoint is reachable under a Spring Security policy. It does not implement full business login or authorization.

Create the structure:

~~~text
compatibility-lab/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            compatibility/
              CompatibilityApplication.java
~~~

Contents of `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compatibility-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

**What to observe:** The POM only declares the Boot version in `<parent>`. No line hardcodes `spring-security-core=7.1.2`, `spring-security-web=7.1.2`, or a Spring Framework version. The parent manages these dependencies; you only choose the appropriate *starters*.

Create `src/main/java/com/example/compatibility/CompatibilityApplication.java`:

~~~java
package com.example.compatibility;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CompatibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompatibilityApplication.class, args);
    }

    @GetMapping("/status")
    public String status() {
        return "compatible";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/status").permitAll()
                .anyRequest().authenticated());
        return http.build();
    }
}
~~~

The snippet above uses the modern Java configuration API: creating a `SecurityFilterChain` instead of relying on `WebSecurityConfigurerAdapter`, which was removed in newer lines. This is a **complete main-class** Spring Boot application program that does not require a database or another controller to serve `/status`.

Prerequisites before running: JDK 21 installed, a compatible Maven version, and access to Maven Central on the first run to fetch dependencies.

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

In a second terminal, call:

~~~bash
curl -s http://localhost:8080/status
~~~

Expected response body:

~~~text
compatible
~~~

Do not assume the entire startup log will look identical on every machine; logs also depend on JVM version, operating system, and configuration. If another application holds port 8080, change the port before running. Endpoints other than `/status` still go through the `authenticated()` rule.

**Do not hardcode a login password into source code just to test compatibility.** Spring Security can generate a test user/password via auto-configuration, but proving compatibility in this lesson only requires the declared public endpoint and the dependency graph.

### Checking the Exact Security Version in Maven

In the directory containing the POM, run:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Look for Spring Security artifacts such as `spring-security-core`, `spring-security-config`, and `spring-security-web`. With the Boot 4.1.2 reference set, Spring Security modules are managed by the Boot BOM at **7.1.2**. You do not need to memorize every log line; what matters is checking that **the modules belong to the same line and no stray version was pulled in by another dependency**.

You can also inspect the effective POM assembled by Maven:

~~~bash
mvn help:effective-pom
~~~

If the Boot parent is configured properly, `dependencyManagement` entries will appear in the effective POM even though you did not write that list in the original POM.

## 5. Gradle Example: Same Version Set as Maven

Gradle uses a different declaration syntax; the rules remain the same: pick the Java toolchain, the Boot plugin, and the **BOM** so Spring Security modules receive unified versions.

A sample `build.gradle` for the same Java 21 and Boot 4.1.2 application:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Here `platform(...BOM_COORDINATES)` explicitly imports the BOM into Gradle's dependency configurations. If a project uses the `io.spring.dependency-management` plugin per Boot's guide, that plugin can also apply the BOM, though you should avoid mixing multiple unintended override configurations.

**Choose a Gradle wrapper** supported by Boot 4.1.2: 8.x from 8.14 onward or 9.x. Verify with:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew bootRun
~~~

On Windows, use `gradlew.bat` instead of `./gradlew`. These commands assume the wrapper already exists. If there is no wrapper, generate the project from Spring Initializr or generate the wrapper with a suitable Gradle version.

The `dependencyInsight` command is useful when you need to know **why** a version was selected: it displays dependency relationships and constraints/selection reasons per configuration. Observing the actual resolved output matters more than looking solely at the `implementation` line.

### How Do Maven Parent and Maven BOM Differ?

- Inheriting `spring-boot-starter-parent`: receives **dependency management** along with many default Boot plugin/build configurations.
- Only `import`ing `spring-boot-dependencies` as a BOM: receives **dependency version management**, without automatically inheriting all plugin configurations of the starter parent.
- Gradle: the Boot plugin supports packaging/running; aligning dependencies can use the dependency-management plugin or Gradle's explicit `platform` mechanism. Do not assume that any `plugins { id 'org.springframework.boot' }` block automatically applies all BOM constraints under every configuration style.

If a company requires a custom parent, you can import the Boot BOM via `dependencyManagement`, while managing Maven plugin versions and packaging properly yourself.

## 6. Spring Initializr: Choose Right Once, Verify Many Times

At [https://start.spring.io/](https://start.spring.io/), a common workflow is:

1. Select **Maven** or **Gradle**, language **Java**.
2. Select a **Spring Boot stable** version from the list; for this lesson you can compare against Boot 4.1.2.
3. Select **Java 21** and ensure the machine has the matching JDK.
4. Add the **Spring Security** and **Spring Web MVC** dependencies (display names in the UI may vary by line).
5. Generate the project, unzip it, and inspect `pom.xml`/`build.gradle`.
6. Run `java -version`, `mvn -version`, or the Gradle wrapper to confirm the actual tools.
7. Build and inspect the dependency graph as shown above.

Initializr creates a consistent configuration at project generation time, but **it does not guarantee that libraries you add later will always be compatible**. When copying a dependency from an old tutorial into the project, check whether it is already managed by Boot and whether it forces a different Spring Framework or Security version.

If you use `spring-boot-starter-webflux` for a reactive stack instead of Web MVC, you must choose the WebFlux security configuration model (`SecurityWebFilterChain`) rather than copying `HttpSecurity`/servlet filters directly.

## 7. Common Places Where Versions "Drift" Even When the POM Looks Valid

### 7.1. Pinning a Separate Security Version While Using the Boot BOM

An example to watch out for:

~~~xml
<!-- Do not pin this version separately without a valid reason and compatibility testing. -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.2.0-RC1</version>
</dependency>
~~~

If the rest is managed by Boot 4.1.2 at 7.1.2, the project risks mixing 7.2 RC and 7.1 stable. Maven may pick one version via dependency mediation; compiling cleanly does not prove that runtime APIs and behavior are consistent.

When you genuinely need a different Security version for a vulnerability fix or feature, consult the official override instructions, change **all related modules consistently**, run integration tests, and consider upgrading to a Boot patch that includes a newer BOM. Do not patch one isolated module and guess that it is enough.

### 7.2. Upgrading the JDK Without Upgrading Gradle/Maven/Plugins

`java -version` may report Java 21 while `./gradlew --version` uses a different JVM, an outdated wrapper, or plugins lacking support. Check all of them:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

Run only the commands matching your chosen build tool. An IDE can use one JDK to run the Gradle daemon and another JDK to compile; therefore inspect IDE settings, `JAVA_HOME`, Java toolchain, and the CI runner.

### 7.3. Mixing Namespaces and Stacks Across Major Versions

Spring Boot 3+ applications live in the Jakarta EE ecosystem, using `jakarta.*` APIs instead of the older `javax.*`. Spring Boot 4 moves up to the Spring Framework 7 generation and newer servlet containers/APIs. A library that still depends on older Servlet APIs or the `javax.servlet.*` namespace can cause build or runtime errors.

Do not assume that changing imports is enough to upgrade a large application: plugin configurations, Jakarta APIs, custom Security code, reflection libraries, Servlet filters, tests, and annotations may all need adjustments.

### 7.4. Relying on a Tutorial from a Different Branch

For instance, a Spring Security 5 tutorial uses `WebSecurityConfigurerAdapter` or `authorizeRequests()`/legacy APIs. Copying such code into Spring Security 7 may fail to compile or produce unintended behavior. When studying, open documentation for the exact major version of your application and pay close attention to API names in examples.

### 7.5. Ignoring Security Updates When a Newer Stable Release Exists

"Boot 4.1.2" is a **snapshot on a specific date**, not a promise that it will always remain the latest. Spring releases Security patches for CVEs and may update the Boot BOM afterward. When taking a project to production, check security advisories, support timelines, dependency scans, and your patch update plan.

## 8. Distinguishing Three Commonly Confused Java Versions

| Concept | What is it? | Example |
| --- | --- | --- |
| **JDK running the build tool** | The JVM launching Maven/Gradle/IDE plugins | CI runner executes Maven using JDK 21 |
| **Java source/bytecode target** | The language level and class file version emitted by the compiler | `<java.version>21</java.version>` or Gradle toolchain 21 |
| **Production JVM** | The actual virtual machine running the JAR after deployment | Container image provides Java 21 |

If bytecode is compiled for Java 21 and then run on JVM 17, you can hit `UnsupportedClassVersionError`, even though both Java versions are supported by Boot when each is configured **consistently on its own**. "Boot supports Java 17+" does not mean an application built for Java 21 will run backward on Java 17.

A Java toolchain selects a consistent compiler, but does not by itself verify that the Docker image has the matching JVM. In Docker/CI, use an appropriate JDK image at build time and a sufficiently new runtime image; run a smoke test after packaging.

Choosing a JDK for production also involves vendor LTS timelines, security patches, container base image support, memory footprint, and real-world performance. Prefer a runtime that your organization patches regularly.

## 9. Compatibility Testing and Troubleshooting

A minimum verification checklist before locking in a stack:

| Check | Command / Method | Meaning |
| --- | --- | --- |
| JDK in use | `java -version`, `mvn -version` / `./gradlew --version` | Is the right JVM used for building |
| Compile/package | `mvn clean package` or `./gradlew build` | Are code and plugins compatible |
| Dependency graph | `mvn dependency:tree` / `./gradlew dependencyInsight` | Are Security/Framework modules mixed |
| Boot start | `mvn spring-boot:run` / `./gradlew bootRun` | Does auto-configuration initialize properly |
| Public endpoint | `curl` to `/status` in the example | Do basic web requests work |
| Protected endpoint | Call a URL requiring authentication | Is the security filter chain registered |
| Security tests | MockMvc/WebTestClient, authentication/authorization tests | Verifies security rules, not just app startup |
| Dependency & CVE audit | Dependency scanning tools and official advisories | Are safe patched versions in use |
| Staging runtime | Run JAR in production-like image/VM | Any JDK, OS, proxy, or container mismatch |

Some typical errors and how to diagnose the root cause first:

| Symptom | Root Cause to Check First |
| --- | --- |
| `UnsupportedClassVersionError` | Java bytecode target is newer than the runtime JVM |
| `NoClassDefFoundError`, `ClassNotFoundException` | Missing module or package/namespace change, inconsistent runtime classpath |
| `NoSuchMethodError` | Runtime library version differs from the version code compiled against; inspect dependency tree |
| `Failed to introspect Class` or auto-configuration failure | Dependency relying on Spring/Jakarta is no longer compatible |
| Maven reports "release version 21 not supported" | Actual compiler/JDK is too old for the requested release target |
| Gradle plugin fails to load or wrapper errors | Gradle/Java/plugin does not satisfy the version matrix |
| Secured endpoint returns 401/302 | Could be **expected behavior** of Spring Security; check `AuthenticationEntryPoint`, do not assume a version mismatch |

Do not fix library errors by removing Security or disabling CSRF just to get the application to start. Those are separate concerns from version compatibility.

## 10. Upgrading Layer by Layer Without Breaking the Project

When an application is running on an older stack and needs an upgrade, follow a controlled sequence:

1. **Baseline current versions**: record build/runtime JDK, Boot, actually resolved Security, Framework, Gradle/Maven, container, and other Spring libraries.
2. **Read migration guides for every major version crossed**, especially when moving Boot 3 → 4 or Security 6 → 7. Check removed APIs, Jakarta, security configuration, OAuth2, method security, and starters.
3. **Select target Boot and dependency management** per System Requirements/BOM documentation; verify Java and build tool first.
4. **Upgrade patches within the current line if needed** to reach a stable/patched baseline before changing major versions.
5. **Update Java/toolchain, parent/plugin/BOM, and starters** as one testable change; avoid forcing a standalone Security version.
6. **Run compile and unit/integration/security tests**; inspect the dependency tree and test authentication, authorization, session, CSRF, OAuth2, or JWT as applicable.
7. **Deploy to staging** with production-equivalent JVM and container; measure startup, latency, login flows, and health endpoints.
8. **Monitor and keep a rollback path** in case of behavior changes or incompatible dependencies.

Not every project needs an immediate major upgrade. However, when vulnerabilities or end-of-support occur, keeping old code cannot be justified by saying "the app still runs."

### Why Not Upgrade Spring Security Alone?

Spring Security interacts tightly with Spring Framework, Spring Boot auto-configuration, servlet/webflux runtimes, authentication, HTTP headers, method interception, and other dependencies. Letting Boot manage Security gives you a combination tested by Boot. Going outside the BOM means you explicitly take on responsibility for compatibility testing and risk control.

For an urgent security patch, an override can occasionally be necessary. Still, that must be a documented, tested decision; adding `<version>` based on an online snippet should not be treated as the standard upgrade method.

## 11. Three Scenarios to Practice Choosing a Version Set

**Scenario A — New project; developer machines and production have JDK 21 and Maven 3.9; only a servlet REST API and basic security are needed.**

You can choose Boot **4.1.2**, Security **7.1.2** via the Boot BOM, `spring-boot-starter-webmvc`, and `spring-boot-starter-security`. Use Java 21 and the Boot Maven parent; do not declare a separate Spring Security version. Add a smoke test and verify the runtime/container JDK before deployment.

**Scenario B — Existing application on Spring Boot 3.5, depending on an internal library tested with Spring Framework 6.2 and JDK 17.**

Prioritize checking the maintained Boot 3.5 patch release and using the corresponding Security version from its BOM. The reference set as of writing is Boot **3.5.16** + Security **6.5.11**, running on Java 17. If you want to upgrade to Boot 4, inspect the internal library and the impact of Spring Framework 7, Jakarta/Servlet, and tests; do not change only the Security version to 7.1 and assume compatibility.

**Scenario C — Developer machine has Java 27 installed, while the project is still on Boot 3.5.16.**

Boot 3.5.16 documentation states compatibility up to **Java 25**, so **you cannot conclude Java 27 is a supported combination** just because a few commands run. Use a JDK within the published range, or prepare to upgrade the Boot line after checking constraints and dependencies.

**Scenario D — An online tutorial requires Spring Security 5.8 while the new system uses Boot 4.1.**

Do not copy the POM/APIs verbatim from that tutorial. Find a guide matching the Spring Security 7 major version, using starters/BOM and modern configuration APIs. If you encounter an old dependency, look for a newer version or remove unnecessary dependencies.

## 12. Stack Selection Checklist and Common Pitfalls

Before marking a combination as "compatible", confirm each item:

- [ ] Read **System Requirements for the exact Spring Boot version** you plan to use.
- [ ] Both build Java and runtime Java are within the supported range; bytecode does not exceed the production JVM.
- [ ] Maven/Gradle wrapper and plugins match required versions.
- [ ] Boot parent or BOM is applied consistently; Spring modules resolve uniformly.
- [ ] Checked the Spring Security version in **Managed Dependency Coordinates**, rather than guessing from the starter name.
- [ ] Chose the right Web MVC/Servlet or WebFlux/Reactive stack and matching security APIs.
- [ ] If using Spring Cloud, selected a compatible Cloud release train.
- [ ] Did not accidentally pull an RC, SNAPSHOT, or different major version of Security/Framework into a stable project.
- [ ] Executed build, startup, security tests, and inspected the dependency graph.
- [ ] Reviewed release notes, security advisories, and support lifecycle before production.

Common mistakes to avoid:

1. **"Spring Boot 4 always requires Java 21."** Incorrect for Boot 4.1.2: official documentation states a minimum of Java 17.
2. **"Java 27 runs every Spring Boot 3.x release."** Do not extrapolate from a higher Java version; Boot 3.5.16 only documents compatibility up to Java 25.
3. **"Picking Boot 4.1.2 and pinning Security 6.5 yourself is optimal."** Risks major/framework mismatch. Under the default BOM, Boot 4.1.2 manages Security 7.1.2.
4. **"Using `spring-boot-starter-security` requires declaring a separate Security version."** When the Boot parent/BOM is applied properly, it does not.
5. **"Just adding the Boot Gradle plugin aligns every dependency automatically."** You must verify the BOM/dependency management mechanism configured in Gradle.
6. **"A successful build proves security is configured correctly."** No: you still need to test authentication, authorization, and production configuration.
7. **"With the latest major version, all old libraries remain compatible."** No: libraries outside the Boot BOM may need upgrades.
8. **"An RC has a higher version number, so it should always be used."** No: RCs are for upgrade testing, not automatically the stable choice.
9. **"Getting 401 after adding Spring Security means the version is wrong."** That may simply be default protection working as designed.
10. **"Maven parent and BOM are the same thing."** A parent also manages plugin/build defaults; a BOM primarily manages dependency versions.

## 13. Self-Check Questions

**Question 1.** A project uses Boot 4.1.2, Java 21, and `spring-boot-starter-security`. Do you need to add `<version>7.1.2</version>` for `spring-security-core`?

*Answer:* Not if the Boot parent/BOM is used properly. Boot 4.1.2 manages Spring Security 7.1.2. Override only with a specific reason, compatibility documentation, and testing.

**Question 2.** You want to build a Spring Boot 4.1.2 app, the Gradle wrapper is 8.5, and Java 21 is installed. Is that sufficient?

*Answer:* Not yet. Boot 4.1.2 specifies Gradle 8.14+ in the 8.x line, or Gradle 9.x. Update the wrapper appropriately first.

**Question 3.** Why are Boot 3.5.16 and Security 6.5.11 a sound combination, whereas Boot 3.5.16 + Security 7.1.2 should not be assumed?

*Answer:* Because Boot 3.5.16's Managed Dependency Coordinates manage Security 6.5.11 alongside Framework 6.2; Security 7 belongs to a different generation and requires official compatibility verification.

**Question 4.** An application built with Java 21 fails with `UnsupportedClassVersionError` when running its JAR on Java 17. What is the likely issue?

*Answer:* The bytecode target is newer than the runtime JVM. Boot supporting both JDKs independently does not mean Java 21 bytecode runs on JVM 17.

**Question 5.** What proves that the resolved Security version is actually 7.1.2 rather than another version pulled in by a library?

*Answer:* The dependency graph / effective BOM of the actual build—such as `mvn dependency:tree` or Gradle `dependencyInsight`—not just a reference table or starter name.

**Question 6.** Why does a Boot 4.1 project use `spring-boot-starter-webmvc` in the example, whereas Boot 3.5 uses `spring-boot-starter-web`?

*Answer:* Boot 4 reorganized web modules/starters with an explicit Web MVC choice; when switching lines, follow the documentation and metadata of that exact version instead of blindly pasting old artifacts into new examples.

**Question 7.** To fix a Spring Security CVE, is it enough to just add the latest version to each reported module?

*Answer:* No. Read the advisory, choose a patch compatible with your stack, prefer updating the Boot BOM/patch when available, keep all Security modules on the same generation, and run full tests.

When starting a project, treat the **Java → Spring Boot → Spring Security** set as an engineering decision verified via **System Requirements + Boot BOM + dependency graph + real tests**. A good version set is one that fits your environment, has an upgrade path, and receives patches—not simply the three highest numbers on download pages.

### Official Sources for Updates

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security — Hello Spring Security (Servlet)](https://docs.spring.io/spring-security/reference/servlet/getting-started.html)
- [Spring Security Advisories](https://spring.io/security/)
- [Spring Boot release notes](https://github.com/spring-projects/spring-boot/wiki)
