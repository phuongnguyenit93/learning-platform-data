# Building a Compatibility Matrix Before Upgrading Java, Spring Boot, or Build Tools

## 1. Why Do We Need a Compatibility Matrix?

Upgrading Java, Spring Boot, Maven, or Gradle is a change with interdependent relationships. A project may compile with a new JDK while the Maven Wrapper cannot run on that JDK; Spring Boot may support a new Java version while the Spring Cloud release train in use does not yet support it; Gradle core may be compatible while an old build plugin is not yet compatible with a new Gradle major version; an application may produce a JAR while the production runtime or container is too old.

A safe upgrade needs to answer upfront:

- Which JDK runs the Maven or Gradle daemon?
- Which JDK is used to compile, run tests, generate Javadoc, and run the application?
- Which Java version is the bytecode/API target that the artifact must support?
- What levels of Spring Framework, Java, Maven/Gradle, and Servlet container does the target Spring Boot version require?
- Are the Spring Cloud release train, Spring Data, Security, Kafka, Batch, Micrometer, and related BOMs compatible?
- Do the Maven/Gradle Wrapper and each build plugin support the new JDK/build-tool version?
- Are test libraries, annotation processors, static analysis, code generation, Docker builder, and native-image toolchain keeping up?
- Can CI build, test, and package on the target matrix? Which artifact/configuration can be used to roll back?

A **compatibility matrix** is a table recording these relationships, along with confirmation sources, verification status, owners, and decisions. It helps the team see risks before changing versions in the POM or build script.

This guide walks through an example upgrade from Spring Boot 3.5 to Spring Boot 4.1, while explaining how to build a general matrix for a Maven or Gradle project. The specific versions are a snapshot of official documentation looked up on **November 9, 2026**; re-check the requirements/release notes pages when starting a new upgrade cycle.

## 2. Distinguishing Java Version Layers

There is no single "Java version" variable. A project can use different JDKs for different purposes.

| Layer | Question | Where to Configure/Check |
| --- | --- | --- |
| Build JVM | Which JVM runs the Maven or Gradle daemon? | JAVA_HOME, mvn -v, gradle --version, IDE settings |
| Compiler JDK | Which javac actually compiles the source? | Maven Toolchains or Gradle Java Toolchains |
| Test JVM | Which JVM runs unit/integration tests? | Surefire/Failsafe fork, Gradle test launcher/toolchain |
| Bytecode target | Which Java version must class files be able to run on? | Maven maven.compiler.release, Gradle options.release |
| Application runtime | Which JRE/JDK does the production container/VM use? | Docker base image, deployment manifest, server config |
| Native-image toolchain | Which GraalVM/native build tools version? | Native Build Tools, GraalVM, builder image |

Example:

~~~text
Build JVM:          JDK 21
Compiler toolchain: JDK 21
--release target:   Java 17
Test JVM:           JDK 21
Production runtime: Java 17
~~~

This is a valid configuration if every framework/plugin supports that combination. A JDK 21 compiler can produce Java 17 bytecode and verify Java 17 APIs using `--release 17`. However, this does not automatically guarantee that Maven/Gradle plugins, annotation processors, or the framework runtime are compatible.

### 2.1. Build JVM Differs from Compiler Toolchain

`java -version` shows the Java executable found by the shell. `mvn -v` shows the Java runtime Maven is using. `./gradlew --version` displays the JVM running Gradle. An IDE can configure its own Gradle JVM, separate from `JAVA_HOME`.

Maven Compiler Plugin can select a JDK via Maven Toolchains; Gradle has Java Toolchains. Therefore, a machine can run Maven on Java 17 while compiling/testing with JDK 21 if the project configures it explicitly.

**Do not infer the compile target from JAVA_HOME.** Check the build JVM, compiler toolchain, and `--release`.

### 2.2. Source/Target Differs from --release

For the Java compiler:

- `source` controls the syntax/language level.
- `target` controls the class-file bytecode version.
- `--release` controls the language rules, bytecode target, and allowed Java SE APIs.

Setting only `source=17` and `target=17` does not prevent source code from calling APIs introduced only in Java 21 if the compiler JDK is 21. `--release 17` checks the Java 17 API surface as well. Use a toolchain to choose the compiler JDK, and use `--release` to specify the compatibility target.

## 3. Reading the Spring Boot Requirements Matrix

Spring Boot publishes system requirements for each version line. As of the lookup date November 9, 2026, the official documentation for the two illustrative lines states:

| Component | Spring Boot 3.5.16 | Spring Boot 4.1.x (4.1.2 docs) |
| --- | --- | --- |
| Minimum Java | 17 | 17 |
| Maximum documented Java | 25 | 27 |
| Minimum Spring Framework | 6.2.19+ | 7.0.10+ |
| Maven | 3.6.3+ | 3.6.3+ |
| Gradle | 7.6.4+ or 8.4+ in the 8.x line | 8.14+ in the 8.x line or 9.x line |
| Servlet container baseline | Servlet 5.0+; embedded Tomcat 10.1, Jetty 12.0, Undertow 2.3 | Servlet 6.1+; embedded Tomcat 11.0, Jetty 12.1 |

Sources: [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html) and [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).

**How to read the table:** Java 17 is the minimum runtime for both example lines; that does not mean every third-party dependency supports Java 17 or Java 27. Spring Boot documentation also notes that third-party projects may impose higher requirements.

Do not use this table as a substitute for a migration guide. It only answers platform/build-tool requirements at the Spring Boot level; it does not check plugins, drivers, libraries, application servers, native-image, or API changes in project code.

### 3.1. Do Not Mix Requirements Between Lines

Spring Boot 3.5.16 lists Gradle 7.6.4+ or 8.4+ in the 8.x line. Spring Boot 4.1.x requires Gradle 8.14+ or 9.x. A project using Gradle 8.3 may work with some older Boot 3.x releases but does not meet the minimum for Boot 3.5.16.

Similarly, the fact that Gradle 9 runs on JDK 17 does not by itself prove that Spring Boot 3.5 supports Gradle 9. You need the intersection of the matrices:

~~~text
Gradle runtime compatibility
             INTERSECT
Spring Boot build-tool support
             INTERSECT
Plugin compatibility
             =
Acceptable build combination
~~~

## 4. Java, Gradle, and Maven Matrix

### 4.1. Which JDK Does Gradle Run On?

Gradle has two separate concepts: the JVM running Gradle and the Java toolchain for compiling/testing. According to the Gradle Compatibility Matrix 9.9.0:

- Gradle 9.9 runs on Java 17 through Java 27 JVMs.
- Java 25 has toolchain support starting in Gradle 9.1.0.
- Java 26 has toolchain support starting in Gradle 9.4.0.
- Java 27 has toolchain support starting in Gradle 9.8.0.
- Gradle 8.14 supports a Java 24 toolchain; Java 25 and higher require a newer Gradle line according to the compatibility table.

Source: [Gradle Compatibility Matrix 9.9](https://docs.gradle.org/9.9.0/userguide/compatibility.html).

This explains why you need to separate the `Gradle JVM` and `Java toolchain` columns. A Gradle version may run on JDK 17 without yet supporting a Java 27 toolchain; or the toolchain may compile newer Java while the daemon JVM still requires a different version.

### 4.2. Maven Core and Plugins Have Separate Requirements

Maven core, Maven Compiler Plugin, Surefire/Failsafe, Spring Boot Maven Plugin, Enforcer, and extensions have their own versions and release cycles.

The Maven documentation looked up states that Maven 3.10.0 requires JDK 8 or higher; the Maven 4.0.0-rc-7 line requires Java 17. Maven 4 introduces major changes, and the migration documentation describes how to prepare, run parallel trials, and then switch over completely.

Sources: [Maven Releases History](https://maven.apache.org/docs/history) and [Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4).

Therefore, when upgrading Maven:

1. Check the JDK running Maven core.
2. Check the Maven Wrapper distribution.
3. Check the Maven Plugin API/runtime requirements of each plugin.
4. Check extensions, core extensions, and parent POMs.
5. Run the build on the target Maven version before dropping the current version.

Do not assume a plugin supports Maven 4 just because Maven 4 can run on the current JDK. Plugins may depend on changed Maven or Resolver APIs.

## 5. Spring Cloud and Spring Projects Matrix

The Spring Boot BOM manages a set of compatible Spring dependencies, but Spring Cloud projects have their own release train. You must choose the right Cloud train for the Boot generation.

Published Spring Cloud compatibility table:

| Spring Cloud release train | Spring Boot generation |
| --- | --- |
| 2025.1.x (Oakwood) | Boot 4.0.x; Boot 4.1.x starting from 2025.1.2 |
| 2025.0.x (Northfields) | Boot 3.5.x |
| 2024.0.x (Moorgate) | Boot 3.4.x |
| 2023.0.x (Leyton) | Boot 3.2.x; Boot 3.3.x from 2023.0.2 |
| Older trains marked with * | End of life / out of support according to the project page |

Sources: [Spring Cloud project – Release Train compatibility](https://spring.io/projects/spring-cloud/) and [Spring Cloud 2025.1.2 release notes](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/).

If a project moves from Boot 3.5 to Boot 4.1, do not keep Spring Cloud 2025.0.x and only change the Boot parent. You need to pick the 2025.1.x train and verify the specific service release in the reference docs/release notes before pinning a version. A release train may add compatibility in a service release; do not look only at the year number or train name.

### 5.1. BOMs and Modules to Review

Depending on the application, the matrix may include:

- spring-boot-dependencies or Spring Boot parent.
- spring-cloud-dependencies.
- Spring Data BOM.
- Spring Security.
- Spring for Apache Kafka / Spring AMQP.
- Spring Batch, Spring Integration, Spring Modulith.
- Micrometer, Micrometer Tracing, Reactor.
- Spring AI or Spring GraphQL if used.

Do not arbitrarily override spring-core, spring-context, spring-web, spring-test, or dependencies managed by the Boot BOM. If a library requires a different version, check the compatibility of the entire dependency graph and the reason for the override.

### 5.2. Framework Compatibility Is Not Just Compilation

An application may compile yet fail at startup due to auto-configuration, bean conditions, property renames, or integration libraries. Also check:

- The Spring Boot migration guide for the major/minor version.
- Spring Framework migration notes.
- Spring Cloud release train and compatibility verifier.
- Spring Security filter chain, OAuth/JWT integration.
- Spring Data repository/query behavior and database driver.
- Servlet/Jakarta namespace, container version, and deployment model.
- Serialization, HTTP client, messaging protocol, and configuration changes.

For a major upgrade, there must be integration tests on the real runtime or a production-equivalent environment.

## 6. Which Axes Should a Compatibility Matrix Cover?

A useful matrix covers more than just Java, Boot, and the build tool. At a minimum, consider these groups:

| Group | Versions/Attributes to Record |
| --- | --- |
| Java | Build JVM, compiler JDK, test JVM, bytecode target, production runtime, vendor/architecture |
| Spring | Boot, Framework, Cloud train, Data/Security/Integration/Kafka/Batch |
| Build system | Maven/Gradle core, Wrapper, JDK runtime, toolchains |
| Build plugins | Compiler, Surefire/Failsafe, Enforcer, Boot plugin, Kotlin, codegen, quality tools |
| Dependencies | BOMs, test libraries, logging, ORM, HTTP clients, database drivers |
| Runtime platform | Tomcat/Jetty/Undertow, servlet/Jakarta level, OS, libc, CPU architecture |
| Container/native | Docker/Buildpacks builder, run image, GraalVM, Native Build Tools |
| CI | Runner image, JDK installations, cache, network/mirror, parallelism |
| IDE/developer | IntelliJ/Eclipse version, IDE build JVM, local wrapper behavior |
| Operations | TLS/truststore, certificates, secrets, deployment manifests, monitoring/agents |

Each row should have a status and evidence. Example:

| Component | Current | Target | Evidence | Status |
| --- | --- | --- | --- | --- |
| Build JVM | JDK 17 | JDK 21 | mvn -v, CI image | Verify |
| Bytecode target | Java 17 | Java 17 | Compiler configuration | Keep |
| Spring Boot | 3.5.16 | 4.1.2 | Official requirements + migration guide | Verify |
| Spring Framework | 6.2.x (Boot-managed) | 7.0.10+ (Boot-managed) | Boot BOM/effective POM | Verify |
| Spring Cloud | 2025.0.x | Matching 2025.1.x service release | Spring Cloud compatibility table | Verify |
| Maven | 3.9.x | 3.10.x | Maven Wrapper + plugin requirements | Verify |
| Gradle (if used) | 8.x | 9.x or 8.14+ | Gradle/Boot compatibility matrix | Verify |
| Compiler/Surefire plugins | Current version | Target-compatible version | Plugin system requirements/release notes | Verify |
| Container runtime | Tomcat 10.1 / Servlet 6.0 | Tomcat 11 / Servlet 6.1 if using Boot 4 | Runtime image and deployment docs | Verify |

The Current values here are illustrative examples; replace them with real data from the repository. Do not copy the sample table and treat it as an audit result.

### 6.1. Statuses to Use

Define consistent statuses across the team:

- SUPPORTED: confirmed by official documentation and the combination is verified by CI.
- TESTED: build/tests have run on the combination, but there is not yet enough production evidence.
- NEEDS_CHECK: documentation or plugin status is unclear.
- BLOCKED: non-overlapping version requirements or failing tests.
- NOT_USED: the project does not use that component.
- DEPRECATED/EOL: version has reached end-of-life or is about to be removed.

Do not mark SUPPORTED solely because the build passed on a personal machine. Save documentation links, CI runs, test reports, and the verification date.

## 7. Building the Matrix from the Current State

Before editing files, record a reproducible baseline:

~~~bash
java -version
javac -version
./mvnw -version
./gradlew --version
docker version
~~~

Run the commands appropriate for your project's build system. A project is not required to have both Maven and Gradle.

### 7.1. Maven Inspection

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree
./mvnw help:active-profiles
./mvnw -B -ntp clean verify
~~~

Record:

- Parent POM and Spring Boot version.
- Maven Wrapper distribution.
- Compiler release/toolchain.
- Plugin versions after merging from parent.
- Resolved dependency versions.
- Active profiles and repository/mirror.
- Test results, warnings, deprecations, and build duration.

### 7.2. Gradle Inspection

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew tasks --all
./gradlew clean check
~~~

When you need to know which version was selected and why:

~~~bash
./gradlew dependencyInsight \
    --dependency spring-core \
    --configuration runtimeClasspath
~~~

Record:

- `gradle-wrapper.properties` distribution URL/checksum.
- JVM running the daemon and Java toolchain.
- Plugin versions in the `plugins` block and version catalog.
- Dependency constraints/platform/BOM.
- Task graph, test workers, and warnings.
- Cache, configuration cache, and build scan if the organization uses them.

### 7.3. Reading the Dependency Tree Instead of Only Looking at Build Files

A POM/`build.gradle` may declare dependencies without direct versions because a BOM or plugin management manages them. The final version chosen by the resolver is what the application runs.

Maven:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
~~~

Pay attention to dependency mediation, version constraints, exclusions, optional dependencies, and transitive dependencies. A dependency may be pulled in by a plugin/test library rather than appearing directly in the build file.

## 8. Choosing an Informed Target and Creating a Test Matrix

Suppose the current project is:

~~~text
Spring Boot:      3.5.x
Java runtime:     17
Bytecode target:  17
Maven Wrapper:    3.9.x
Spring Cloud:     2025.0.x (if used)
Production:       Java 17 container
~~~

Proposed target:

~~~text
Spring Boot:      4.1.x
Java runtime:     17 or 21 (per runtime policy)
Bytecode target:  17 if Java 17 compatibility must be kept
Maven Wrapper:    3.10.x
Spring Cloud:     Confirmed 2025.1.x service release
Production:       Tested Java 17/21 image
~~~

This is an example of target selection; not every organization needs to change the build JDK and production runtime at the same time. If the organization must keep the application running on Java 17, you can use a newer JDK to build while keeping `--release 17` after checking that all tools/plugins support it.

### 8.1. Do Not Run a Pointless Full Cross-Product

If a matrix has 3 Boot versions × 4 JDKs × 3 Gradle versions × 2 OSes × 2 architectures, that is 144 combinations. Not every combination needs to run on every commit.

Divide the matrix into tiers:

- Required build: the official target, run on every pull request.
- Compatibility smoke: a few other JDK/runtime combinations to verify the support window.
- Migration lane: current and target stacks running in parallel during the upgrade phase.
- Nightly/weekly: less common OS/architecture/plugin combinations.
- Release gate: full integration, packaging, security, and deployment tests.

Choose combinations based on support policy, traffic, runtime fleet, and risk; clearly record which combinations are automatically tested and which are only confirmed by documentation.

## 9. Upgrading Java in a Controlled Manner

Before upgrading Java, check:

1. Framework and Spring Boot support the target JDK.
2. Maven/Gradle core can run on the new JDK.
3. Compiler/toolchain plugin selects the right JDK.
4. Annotation processors (Lombok, MapStruct, Querydsl...) support the new compiler.
5. Test libraries and bytecode tools (Mockito, Byte Buddy, JaCoCo, ASM) support the new class files.
6. Native libraries, JDBC drivers, cryptography providers, and monitoring agents support the runtime.
7. Docker base image and OS architecture provide the right JRE/JDK.
8. IDE and CI runners select the JDK the same way.

### 9.1. Maven Compiler Plugin: Pinning Release

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

With the Spring Boot parent, `java.version` is the convention used by the parent for compiler configuration; `maven.compiler.release` explicitly sets the bytecode/API target. Check the effective POM to confirm the plugin actually receives this value.

### 9.2. Maven Toolchains

The Maven runtime and compiler JDK can differ. The user file `~/.m2/toolchains.xml` (Windows: `%USERPROFILE%\.m2\toolchains.xml`) can register JDKs:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

The path above is an example for Linux; replace it with the real JDK path. The project needs to configure Maven Toolchains Plugin and a compiler plugin that supports toolchain selection. Do not commit personal machine paths into the POM.

### 9.3. Gradle Java Toolchains and Release

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchains select the JDK for supported tasks; `options.release` restricts the API and bytecode target. When upgrading to Java 21, change both the toolchain and release only when product policy allows dropping Java 17 runtime compatibility.

### 9.4. Checking Class Files

If you suspect a dependency was compiled with a higher Java version than expected:

~~~bash
javap -verbose -classpath target/classes com.example.Application
~~~

Look for `major version` in the output. Some common values:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 27 | 71 |

Running `javap` on one class only checks that class. To inspect the entire dependency graph, use `jdeps`/appropriate artifact analysis and run tests on the minimum supported runtime.

## 10. Upgrading Maven/Gradle Wrapper and Plugins

The wrapper ensures every developer and CI uses the same build-tool distribution. However, the wrapper does not automatically upgrade plugins.

### 10.1. Maven Wrapper

The file `.mvn/wrapper/maven-wrapper.properties` specifies the Maven distribution. After selecting the target version, update the wrapper using the Maven Wrapper Plugin or the mechanism used by the team; commit both the wrapper scripts and properties per repo standards.

Verify:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Maven Enforcer can lock down Maven and the Maven Java runtime:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-environment</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9.0,4.0.0)</version>
                    </requireMavenVersion>
                    <requireJavaVersion>
                        <version>[17,28)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The version ranges above are only examples for a Maven 3 + Java 17–27 policy. If the organization chooses Maven 4, update the range and verify plugins/extensions first. `requireJavaVersion` checks the JVM running Maven; it does not replace checking the compiler toolchain or bytecode target.

### 10.2. Gradle Wrapper

The file `gradle/wrapper/gradle-wrapper.properties` contains the distribution URL. Example:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

If the organization pins `distributionSha256Sum`, update it with the checksum taken from the official release page for that exact distribution. Do not fabricate or guess checksums.

Run:

~~~bash
./gradlew --version
./gradlew help
./gradlew clean check
~~~

Also check the plugin DSL, `pluginManagement`, version catalog, convention plugins, `buildSrc`, and included builds. A third-party plugin may require an older Gradle version or may not yet support Gradle 9 even though Gradle core is JDK-compatible.

### 10.3. Plugin Inventory

List versions and owners for at least:

- Spring Boot Maven/Gradle Plugin.
- Maven Compiler Plugin / Gradle Java plugin.
- Surefire/Failsafe / Gradle Test.
- Maven Enforcer.
- Kotlin plugin and Kotlin compiler if present.
- Lombok, MapStruct, Querydsl, and annotation processors.
- JaCoCo, Checkstyle, SpotBugs, PMD, Error Prone.
- Jib, Buildpacks, Docker, Native Build Tools.
- OpenAPI/code generation, protobuf, Avro, frontend/node plugins.
- Maven extensions, Gradle init/convention plugins.

For each plugin, check minimum Maven/Gradle, JDK runtime, API changes, deprecations, and compatible versions of dependent plugins. Do not just update a plugin to `latest` without reading release notes.

## 11. Spring Boot Major Upgrade: Coordinated, Controlled Changes

Upgrading from Boot 3.x to Boot 4.x is a major generation change. You must review the migration guide and dependency stack, not just change the parent version.

Areas commonly needing inspection:

- Spring Framework generation and API changes.
- Spring Cloud release train.
- Jakarta EE/Servlet APIs and container version.
- Spring Security configuration/filter chain.
- Spring Data repositories, persistence providers, and database drivers.
- Jackson/JSON serialization, HTTP clients, validation.
- Observability: Micrometer, tracing, metrics exporters.
- Logging, test libraries, mock frameworks, and test instrumentation.
- Auto-configuration, starters, properties, and custom configuration.

### 11.1. Jakarta Namespace

Spring Boot 3 moved the ecosystem to Jakarta for many former Java EE APIs. When continuing to Boot 4, check the API/container baseline corresponding to the new generation. Do not blindly find/replace `javax` with `jakarta` across all packages: several `javax.*` packages belong to Java SE (for example `javax.crypto`, `javax.net`, `javax.sql`) and remain valid namespaces.

Review compile errors, imports, transitive dependencies, servlet containers, and third-party libraries. Use the migration guide for the exact Boot generation.

### 11.2. Spring Cloud BOM

Maven example:

~~~xml
<properties>
    <spring-boot.version>4.1.2</spring-boot.version>
    <spring-cloud.version>2025.1.2</spring-cloud.version>
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
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This illustrates BOM import for a project that does not inherit from the Spring Boot parent. With the Spring Boot parent, use the dependency management provided by the parent and import the Cloud BOM according to project guidance; do not create unintended duplicate dependency management.

`2025.1.2` is a release train with published compatibility for Boot 4.1.0. When finalizing a version for Boot 4.1.2, check the current service release and the train's compatibility reference. Do not infer that every 2025.1.x service release automatically supports every Boot 4.1.x patch.

### 11.3. Do Not Pin Individual Spring Framework Dependencies to "Fix" Errors

If the Boot BOM manages Spring Framework 7.0.x, manually pinning a Spring 6.2.x module can create a binary mismatch. Check `dependency:tree`/`dependencyInsight`, remove unnecessary overrides, and choose a compatible BOM before forcing individual versions.

## 12. Checking Plugins and Dependencies Outside Spring

Upgrade failures often come from components outside Spring Boot core.

| Category | Example Risk | How to Check |
| --- | --- | --- |
| Annotation processor | Lombok does not understand the new compiler | Run compile/test with target JDK; check release notes |
| Bytecode tools | ASM/Byte Buddy cannot read new class files | Run tests, agents, and instrumentation |
| Coverage | JaCoCo does not yet support new JDK/class version | Run verify and check coverage report |
| Mocking | Mockito/Byte Buddy cannot instrument classes | Test mocks, final classes, inline mock maker |
| Database | JDBC driver/TLS/SQL dialect changes | Integration tests with real DB version |
| Container | Testcontainers/Docker API mismatch | Run tests on CI Docker daemon |
| Security | Spring Security config or crypto provider changes | AuthN/AuthZ regression tests |
| Messaging | Kafka/Rabbit clients or Spring integration mismatch | Contract/integration tests |
| Observability | Micrometer/agent/exporter mismatch | Startup + metrics/tracing smoke tests |
| Code generation | OpenAPI/protobuf/Avro plugin incompatible | Regenerate and inspect diff |
| Native | GraalVM/Native Build Tools incompatible | Native compile and native runtime tests |

**A passing build is not enough.** The plugins above can fail only when running an infrequently used task, generating sources, instrumenting tests, or building a native image. Add those tasks to migration validation if the project uses them.

## 13. Checking Runtime/Container and Deployment Platform

The compatibility matrix must include where the artifact actually runs:

- JRE/JDK vendor and patch version.
- Docker base image/tag/digest.
- Linux distribution, glibc/musl, and CPU architecture.
- Servlet container/Servlet API if deploying a WAR or to an external container.
- Native-image builder and runtime.
- TLS/truststore/certificates, crypto provider, and FIPS mode.
- JDBC driver/database version, broker version, and external services.
- Kubernetes base image, probes, resource limits, environment variables, and secrets.

For example, Boot 3.5 and Boot 4.1 have different Servlet/container baselines in system requirements. If an application deploys a WAR to an external Tomcat, upgrading only the Spring Boot JAR build does not guarantee production Tomcat meets the requirement.

### 13.1. Container Image Matrix

| Attribute | Current | Target |
| --- | --- | --- |
| Image base | Currently running tag/digest | Scanned tag/digest |
| JRE | Java 17 vendor/patch | Tested Java 17 or 21 |
| OS/libc | Current distribution | Target distribution |
| Architecture | amd64 | amd64/arm64 if needed |
| Buildpacks/builder | Builder version | Verified builder version |
| Runtime port | Exposed port | Port/service mapping |
| Health endpoint | Current probe | Tested probe |
| User | UID/GID | Non-root policy |

Do not use the `latest` tag in a release matrix when reproducibility is needed. Pin the digest when container policy requires it, store SBOM/scan results, and test the actual image.

## 14. Step-by-Step Upgrade Process

A reviewable sequence:

1. **Baseline:** lock the current commit, record versions/toolchains/dependency tree, run full tests, and save CI evidence.
2. **Choose target:** determine the Boot/Java/build-tool generation based on official requirements, support policy, and operational deadlines.
3. **Dependency matrix:** verify Spring Cloud/BOMs, third-party libraries, plugins, drivers, and runtime platform.
4. **Build JDK:** standardize the JDK running Maven/Gradle and toolchains across developers/CI.
5. **Wrapper:** upgrade the Maven/Gradle Wrapper in an independent change and run the build on the new version.
6. **Build plugins:** update compiler/test/quality/codegen/container plugins per compatibility docs.
7. **Java target:** decide whether to keep the old bytecode target or upgrade; configure `--release`/toolchain explicitly.
8. **Spring Boot:** upgrade parent/plugin/BOM and matching Cloud train; address the migration guide.
9. **Code/dependencies:** fix API/config/imports, dependency overrides, and deprecated usages.
10. **Verification:** compile, unit tests, integration tests, package, startup smoke, and security/coverage/native tasks if applicable.
11. **CI matrix:** run current and target lanes in parallel; verify caches, artifacts, reports, and runtime images.
12. **Canary/release:** deploy to a production-like environment, observe metrics/logs/traces, and keep a rollback plan.

Some steps can be combined if tightly coupled, such as Boot and the Spring Cloud BOM. However, keep the baseline and test evidence after each milestone so you know which change caused any regression.

### 14.1. Why Upgrade the Wrapper Before Changing Spring Boot?

Upgrading the wrapper independently separates build-system failures from framework failures. If you simultaneously change JDK, Gradle, Boot, Cloud, plugins, and dependency versions, a failed build can have many causes. The order can vary by project; what matters is having evidence at each step and being able to isolate root causes.

### 14.2. When Must Java Be Upgraded Together with Boot?

If the target Boot requires a higher minimum Java than the current runtime, a Java upgrade is mandatory. If both Boot generations support the current Java, you can keep the runtime/bytecode target first to isolate the framework migration. After Boot migration passes, upgrade the Java runtime in a separate change to measure its impact.

## 15. CI Matrix: Verifying in a Real Environment

GitHub Actions example testing Java 17 and 21 for a target build:

~~~yaml
name: compatibility-check

on:
  pull_request:
  workflow_dispatch:

jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
      - name: Verify with Maven Wrapper
        run: ./mvnw -B -ntp clean verify
~~~

This is an example Maven lane. If using Gradle, use the corresponding Gradle setup action/JDK setup and run `./gradlew clean check`. Check action versions against current CI policy.

### 15.1. Current and Target Matrix

| Lane | Boot | Build tool | JDK | Purpose |
| --- | --- | --- | --- | --- |
| Current | Boot 3.5.x | Current wrapper | JDK 17 | Baseline/rollback |
| Target | Boot 4.1.x | Upgraded wrapper | JDK 17 or 21 | Migration validation |
| Compatibility | Boot 4.1.x | Target wrapper | JDK 25 if policy requires | Support-window check |

Not every lane has to run on every pull request. Use a required lane for the target, a nightly lane for the support window, and a release gate for full integration.

### 15.2. CI Cache Must Not Mask Dependency Drift

After changing the Wrapper, JDK, or dependency BOM:

- Check that the cache key includes the appropriate build-tool/JDK/lockfile version.
- Verify the build can resolve dependencies on a cold cache.
- Do not reuse target/Gradle build output from another environment to claim a clean build pass.
- Save dependency lockfiles/verification metadata if the project uses them.
- Record artifact checksums, build commit, and tool versions.

## 16. Evidence Required Before Approving an Upgrade

A migration PR should include concrete evidence:

- Compatibility matrix filled with Current, Target, status, source, and owner.
- Official system requirements/migration guide links.
- Maven/Gradle Wrapper version and build/test/runtime JDKs.
- Effective POM or Gradle dependency report.
- Dependency tree/diff and explained version overrides.
- Compiler release/toolchain config.
- Unit + integration + contract tests.
- Package/JAR/WAR/container image build.
- Application startup/readiness/health smoke test.
- Security/coverage/static analysis/code generation tasks.
- Native-image test if the project uses it.
- CI runs on target JDK/OS/architecture.
- Deployment canary/rollback instructions.

**Do not mark PASS when only compilation passes.** Set statuses layer by layer so reviewers can clearly see what has been verified and what is only based on documentation.

## 17. Troubleshooting Common Compatibility Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Maven fails to start on new JDK | Maven core or extension does not support runtime | `mvn -v`, Maven requirements, and extension versions |
| Gradle daemon reports unsupported Java | Wrapper/Gradle version does not yet support daemon JVM | Gradle compatibility matrix, `./gradlew --version` |
| Compile reports unsupported class version | Dependency/plugin bytecode higher than running JDK | Identify class file version, upgrade runtime or pick compatible dependency |
| Compile passes but production throws UnsupportedClassVersionError | Bytecode target higher than production JVM | Check `--release`, image JRE, and class files |
| NoSuchMethodError/NoClassDefFoundError | Skewed dependency graph or binary incompatibility | `dependency:tree`, `dependencyInsight`, BOM/version overrides |
| Spring application fails to start | Framework/Cloud train/config mismatch or auto-configuration change | Migration guide, condition report, logs, and BOM |
| Spring Cloud compatibility verifier fails | Boot version not in release train | Pick matching Cloud train/service release |
| Servlet API ClassNotFoundException | Incompatible container or Servlet/Jakarta generation | Servlet baseline, embedded/external container |
| Lombok/MapStruct compile fails | Annotation processor does not yet support compiler JDK | Plugin release notes and processor version |
| JaCoCo/Byte Buddy fails | Bytecode instrumentation does not yet support class version | Upgrade plugin/library and run test instrumentation |
| Gradle plugin fails to resolve | Wrong plugin marker/repository/version or plugin unsupported on new Gradle | `pluginManagement`, plugin portal docs, and release notes |
| Maven plugin reports API incompatibility | Plugin does not yet support new Maven core | Plugin system requirements and Maven compatibility plan |
| Build fails only in IDE | IDE build JVM or annotation processing differs from CLI | Sync IDE JDK/Gradle JVM and wrapper |
| Docker image runs locally but fails in production | Different base image, architecture, libc, env, or secrets | Check digest, runtime config, and deployment platform |
| Native build fails after JDK upgrade | GraalVM/Native Build Tools mismatch | Native requirements, builder version, and native smoke test |
| Tests flaky when running in parallel | Shared state/port/database or toolchain race | Unique resources, test isolation, and concurrency limits |
| Dependency version changes even though POM unchanged | BOM, repository metadata, dynamic/SNAPSHOT version, or cache | Pin release, lock dependencies, inspect resolved graph |
| Maven Wrapper downloads wrong distribution | Old `distributionUrl`/mirror/cache | Check `maven-wrapper.properties` |
| Gradle Wrapper checksum mismatch | Distribution altered or wrong checksum | Stop build and verify checksum from Gradle release source |

### Diagnostic Sequence

1. Capture `java -version`, `mvn -v`, or `gradle --version`.
2. Identify the build JVM, compiler toolchain, bytecode target, and production runtime.
3. Check Spring Boot system requirements for the exact version.
4. Check the Spring Cloud train and Spring BOMs.
5. Inspect the effective POM or dependency insight to find actually resolved versions.
6. Verify plugin requirements and wrapper distribution.
7. Run compile/test/package separately to isolate the failing phase.
8. Run application startup and integration tests on the exact runtime/container.
9. Compare current/target CI evidence; do not bypass errors by disabling verifiers or excluding tests.

## 18. Rollback and Rollout

An upgrade is not complete until there is a way back if a production regression appears.

Before deploying:

- Keep the release artifact of the current version and its checksum.
- Save the current Docker image digest/tag.
- Keep the pre-migration deployment manifest/config version.
- Verify whether schema/database migrations are backward-compatible.
- If a DB migration cannot be rolled back, use expand-and-contract: add compatible schema first, deploy code, and only drop old schema in a later release.
- Monitor startup failures, latency, error rate, memory, GC, connection pool, and message lag.
- Define rollback criteria and the responsible owner.

Do not roll back only the JDK/Boot while the artifact was compiled against new APIs or the database schema has changed incompatibly. Rollback must align the artifact, runtime image, configuration, and data migration.

## 19. Project Matrix Template

Copy this structure into your migration issue/PR or release documentation:

| Group | Current | Target | Source Requirement | Actual Evidence | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Build JVM | | | | | | |
| Compiler JDK/toolchain | | | | | | |
| Test JVM | | | | | | |
| Bytecode release | | | | | | |
| Production JRE/JDK | | | | | | |
| Spring Boot | | | | | | |
| Spring Framework | | | | | | |
| Spring Cloud train | | | | | | |
| Maven/Gradle Wrapper | | | | | | |
| Compiler/Test plugins | | | | | | |
| Annotation/codegen plugins | | | | | | |
| Runtime dependencies/BOMs | | | | | | |
| Database/broker drivers | | | | | | |
| Servlet/container | | | | | | |
| Docker/buildpacks/native | | | | | | |
| CI runner/OS/architecture | | | | | | |
| Security/observability agents | | | | | | |
| Deployment/rollback | | | | | | |

Every row must have an owner and evidence before marking complete. If a component is not used, mark `NOT_USED` instead of leaving it blank so reviewers know it was evaluated.

## 20. Hands-On Exercise and Completion Criteria

Practice on an experimental migration branch:

1. Record `java -version`, `javac -version`, `./mvnw -version`, or `./gradlew --version`.
2. Capture the Maven effective POM/dependency tree or Gradle toolchains/dependency insight.
3. Fill in Current for Java build JVM, compiler, bytecode, runtime, Spring Boot/Cloud, wrapper, plugins, dependencies, and container.
4. Choose a target Boot/Java/build tool; find official system requirements and migration guides for that exact version.
5. Confirm the Spring Cloud release train/BOM if the project uses Spring Cloud.
6. Check each plugin (compiler, test, coverage, annotation processor, codegen, container/native) and record source/version constraints.
7. Create a small CI matrix for current and target; keep a baseline lane for comparison.
8. Standardize JDK/toolchain and bytecode release; run clean compile/test.
9. Upgrade the wrapper in a change with evidence; run clean verify/check.
10. Upgrade Boot/BOM and work through the migration guide; run integration/startup tests.
11. Verify the JAR/WAR/container image using the exact production runtime and architecture.
12. Run security/coverage/native tasks if the project uses them.
13. Record any blockers, workarounds, owners, and follow-up version upgrades needed.
14. Create a rollout/rollback plan with artifact digest and database migration strategy.
15. Mark the matrix `SUPPORTED` only when both documentation and CI evidence align; record the verification date.

**Completion criteria:** you can explain the difference between build JVM, compiler toolchain, bytecode target, and runtime; produce a matrix backed by official sources for Boot/Java/Maven/Gradle/Spring Cloud; detect incompatible plugins/dependencies/containers; and provide CI evidence along with a rollback plan before upgrading production.

## Official References

- [Spring Boot 3.5 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Cloud – Release Train Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.2 Release Notes](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/)
- [Gradle 9.9 – Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html)
- [Gradle – JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle – Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Apache Maven – Releases History](https://maven.apache.org/docs/history)
- [Apache Maven – Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4)
- [Apache Maven Compiler Plugin – Setting the --release of the Java Compiler](https://maven.apache.org/plugins-archives/maven-compiler-plugin-LATEST/examples/set-compiler-release.html)
- [Apache Maven – Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven – Plugin Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)
