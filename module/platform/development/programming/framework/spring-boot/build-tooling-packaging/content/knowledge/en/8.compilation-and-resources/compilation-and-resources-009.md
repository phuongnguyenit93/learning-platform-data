# Separating Test Resources from Packaged Resources in Spring Boot (Maven and Gradle)

## 1. Why Separate Resources?

A Spring Boot project contains many files that are not Java code: **application.properties**, YAML, templates, images, SQL migrations, certificates, sample JSON/CSV files, mock data, and test fixtures. Not every file belongs inside the JAR deployed to production.

For example:
- **Configuration and data the application genuinely needs at runtime** belong to *main*.
- **Sample data, mock responses, test properties, and JSON/CSV fixtures** used only by unit tests, integration tests, or Spring Boot test contexts belong to *test*.
- The **executable Spring Boot JAR** must carry required production resources, yet should not drag along test fixtures, test configurations, or test classes.

Proper separation starts with the Maven/Gradle **source layout**. Both tools treat **src/main/resources** and **src/test/resources** as **two separate resource roots** by default. No manual post-packaging deletion step is needed when you follow the conventions and avoid mixing sources.

**Lesson goal:** understand the flow from resource source → resource output → test/runtime classpath → JAR; set up a Spring Boot project; use the test profile properly; verify a clean JAR; handle custom layouts and common pitfalls.

## 2. Two Resource Directories with Different Roles

Convention layout of a Java/Spring Boot application:

~~~text
resource-split/
├── pom.xml                  # used when choosing Maven
├── settings.gradle           # used when choosing Gradle
├── build.gradle              # used when choosing Gradle
└── src/
    ├── main/
    │   ├── java/com/example/resourcesplit/ResourceSplitApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── messages/public.txt
    └── test/
        ├── java/com/example/resourcesplit/ResourceSplitApplicationTest.java
        └── resources/
            ├── application-test.properties
            └── fixtures/test-only.txt
~~~

This directory tree depicts **two alternative build choices**. A real project should choose either Maven or Gradle and keep the matching build files; you do not need all three files `pom.xml`, `settings.gradle`, and `build.gradle` together.

| Location | Purpose | Readable by tests? | Packaged into main/Boot JAR by default? |
| --- | --- | --- | --- |
| **src/main/java** | Production Java source | Yes, via project's main classes | Yes, after compilation |
| **src/main/resources** | Configuration, templates, and runtime data | Yes | **Yes** |
| **src/test/java** | JUnit/Spring test code | Yes | **No** |
| **src/test/resources** | Sample data and test configuration | **Yes** | **No** |

**"Tests can read main resources" does not mean "test resources enter the main JAR".** During testing, the test classpath includes outputs from both main and test. When packaging a standard JAR or executable Boot JAR by default, the build tool includes main outputs and suitable runtime dependencies, excluding test outputs.

If you place **test-only.txt** inside **src/main/resources** even though only tests use it, it becomes a production resource. Placing files in the wrong directory is the most frequent cause of test fixture leaks.

## 3. Resource Flow in Maven

Maven defines standard directories and lifecycle phases. Under the default layout:

~~~text
src/main/resources/**        --process-resources-->       target/classes/**
src/main/java/**             --compile----------->       target/classes/**/*.class

src/test/resources/**        --process-test-resources-->  target/test-classes/**
src/test/java/**             --test-compile------->       target/test-classes/**/*.class

Maven test classpath = test output + main output + required test-scope dependencies

Maven package (plain JAR)  = main classes/resources in target/classes
Spring Boot repackage      = main classes/resources + required runtime dependencies
~~~

Key milestones:

1. The **process-resources** phase uses Maven Resources Plugin to copy/filter main resources into **target/classes**.
2. The **process-test-resources** phase copies test resources into **target/test-classes**.
3. **test-compile** outputs compiled test classes into **target/test-classes** as well.
4. **test** places both main and test outputs on the test classpath to execute unit/integration tests.
5. **package** builds the distributable artifact. For Spring Boot projects configuring `spring-boot-maven-plugin` via the Spring Boot parent, **repackage** builds the executable JAR from the main artifact and runtime dependencies.

**Maven does not sweep the entire `target` folder into the JAR.** **target/test-classes** remains on disk after running tests/package, yet it does not enter the executable JAR. Never conclude "test resources were packaged" simply because they exist in `target/test-classes`.

### Useful Maven Commands

~~~bash
./mvnw clean test
./mvnw package
~~~

- **clean test** clears stale outputs and runs through resource processing, compilation, and tests.
- **package** produces the artifact for inspection.
- On Windows, use **mvnw.cmd**; when a project has no wrapper and a compatible Maven is installed, use **mvn**.

Maven **-DskipTests** skips *executing* tests, not resource separation. Using a test-skipping flag to package without understanding source structure will not keep a fixture mistakenly placed in **src/main/resources** out of the JAR.

## 4. Resource Flow in Gradle

The Gradle Java plugin defines **source sets**. By default, two exist:

- **main**: `src/main/java` + `src/main/resources`.
- **test**: `src/test/java` + `src/test/resources`.

Gradle wires corresponding tasks and outputs:

~~~text
src/main/resources/**   --processResources-->       build/resources/main/**
src/main/java/**        --compileJava-------->       build/classes/java/main/**

src/test/resources/**   --processTestResources-->   build/resources/test/**
src/test/java/**        --compileTestJava----->      build/classes/java/test/**

sourceSets.main.output = main classes + main processed resources
sourceSets.test.output = test classes + test processed resources

test task               -> test runtime classpath (main + test + test deps)
jar task                -> main output
bootJar task            -> main output + main runtime dependencies
~~~

Verification commands with the Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew processResources processTestResources
./gradlew bootJar
~~~

On Windows, use **gradlew.bat**. When running **test**, Gradle automatically runs the tasks needed to prepare main/test classes and resources. **processTestResources** may appear as **UP-TO-DATE** if resources did not change; that does not mean the task was ignored.

In a Boot app, **bootJar** creates the executable JAR. The Spring Boot Gradle Plugin builds the Boot JAR from the **main source set** and main's **runtimeClasspath**, which is why test fixtures and **testImplementation** dependencies stay out of the production artifact.

**Distinguish tasks:** standard **jar** builds a plain JAR from main outputs; **bootJar** builds the Spring Boot executable JAR layout with **BOOT-INF/classes/** and **BOOT-INF/lib/**. Neither blindly copies everything under `build/`.

## 5. Main Resources vs. Test Resources in Spring Boot

Spring Boot supports profile-based configuration loading. Using a **test** profile is a common way to adjust properties when running tests.

In this lab, use:

**src/main/resources/application.properties**

~~~properties
app.label=PRODUCTION
spring.main.banner-mode=off
~~~

**src/main/resources/messages/public.txt**

~~~text
PUBLIC_RESOURCE
~~~

**src/test/resources/application-test.properties**

~~~properties
app.label=TEST_ONLY
~~~

**src/test/resources/fixtures/test-only.txt**

~~~text
TEST_FIXTURE_ONLY
~~~

These files draw a clear boundary:

- **application.properties** and **messages/public.txt** belong to `main`, so they are readable in tests and included in the JAR.
- **application-test.properties** and **fixtures/test-only.txt** belong to `test`, so they appear on the **test runtime classpath** while the main JAR omits them.
- **app.label** in tests switches to **TEST_ONLY** when the `test` profile is active; running the production JAR without that profile or external overrides yields **PRODUCTION**.

**Do not misunderstand the rule:** the filename **application-test.properties** by itself does **not** exclude a file from packaging. An **application-test.properties placed inside `src/main/resources`** is still a *main resource* and will be packaged. It is the **source set location** and build config that determine which artifact includes a resource.

Likewise, **application-prod.yml** in `main` is a runtime config file packaged into the JAR and activated when the `prod` profile is selected. Never delete every file containing **test** in its name via filename patterns without checking where it is used.

### Activating the Test Profile

In a test class, use **@ActiveProfiles("test")** with a Spring Test context to activate the profile configuration. **src/test/resources** only places resources on the test classpath; the directory path alone **does not activate** the `test` profile.

Without initializing a Spring `ApplicationContext`, a plain Java unit test can still read fixtures via the classloader, though **@ActiveProfiles** has no effect without a Spring Test context. Pick the test mechanism that matches what you want to verify.

## 6. Complete Spring Boot Lab (Java 17)

We will build the same program and resources, then choose either Maven **or** Gradle. The example intentionally starts no HTTP server and needs no database so it stays focused on resource handling.

### 6.1. Java Application: Reading Main Resources

Create **src/main/java/com/example/resourcesplit/ResourceSplitApplication.java**:

~~~java
package com.example.resourcesplit;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;

@SpringBootApplication
public class ResourceSplitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceSplitApplication.class, args);
    }

    @Bean
    CommandLineRunner showMainResources(Environment environment) {
        return args -> {
            String label = environment.getProperty("app.label", "MISSING");
            String message;
            try (InputStream input = new ClassPathResource(
                    "messages/public.txt").getInputStream()) {
                message = new String(
                        input.readAllBytes(), StandardCharsets.UTF_8).trim();
            }
            System.out.println("app.label=" + label);
            System.out.println("main.resource=" + message);
        };
    }
}
~~~

This is a **complete Java file**. **ClassPathResource** reads via the classpath, so it works both when running from build directories and when packaged inside an executable Boot JAR. Inside a JAR, you cannot assume the direct filesystem path `src/main/resources/messages/public.txt` exists.

**CommandLineRunner** runs after the Boot context initializes and prints the two expected lines. Because the lab omits the Spring Web starter, it creates no HTTP endpoints and does not bind port 8080.

### 6.2. JUnit Test: Reading Both Main Resources and Test-Only Fixtures

Create **src/test/java/com/example/resourcesplit/ResourceSplitApplicationTest.java**:

~~~java
package com.example.resourcesplit;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ResourceSplitApplicationTest {

    @Autowired
    private Environment environment;

    @Test
    void testResourcesAreAvailableWithoutChangingMainResources()
            throws IOException {
        assertEquals("TEST_ONLY", environment.getProperty("app.label"));
        assertEquals("PUBLIC_RESOURCE", load("messages/public.txt"));
        assertEquals("TEST_FIXTURE_ONLY", load("fixtures/test-only.txt"));
    }

    private static String load(String path) throws IOException {
        try (InputStream input = new ClassPathResource(path).getInputStream()) {
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }
}
~~~

This is also a **complete Java file**, runnable with Spring Boot Starter Test. The test verifies three independent facts:

1. The Spring Test context activated the **test profile** and resolved **TEST_ONLY**.
2. **messages/public.txt** from `main` is present on the test classpath.
3. **fixtures/test-only.txt** from `test` is also present on the test classpath.

When **@SpringBootTest** starts the Spring context, the application's `CommandLineRunner` may also print `app.label=TEST_ONLY` and `main.resource=PUBLIC_RESOURCE` in test logs. Maven/Gradle test-runner output contains additional logs and variable line counts across environments, so verify correctness with **assertEquals**, not by matching full test stdout.

If a fixture file is missing or the profile is inactive, the test fails with an assertion or resource error before packaging.

## 7. Option A: Complete Maven pom.xml

Use the following **pom.xml** with the Java code and resources from sections 5–6:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resource-split</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**Why this configuration suffices:** the Spring Boot parent supplies suitable dependency and plugin management; main and test resource folders are picked up by Maven convention. **spring-boot-starter-test** has scope **test**, keeping test libraries out of runtime packaging. The Spring Boot Maven Plugin builds the executable JAR. **You do not need custom copy/exclude plugins** to keep `src/test/resources` out of the JAR.

From the root directory, run either:

~~~bash
./mvnw clean verify
java -jar target/resource-split-0.0.1-SNAPSHOT.jar
~~~

Or without a Maven Wrapper:

~~~bash
mvn clean verify
java -jar target/resource-split-0.0.1-SNAPSHOT.jar
~~~

On Windows, use **mvnw.cmd** instead of **./mvnw**. **verify** runs through compile, test, and package; on success, the executable JAR has the name shown above for this POM.

**When running the production JAR** with no external overrides or active profiles, the exact two lines printed by the code are:

~~~text
app.label=PRODUCTION
main.resource=PUBLIC_RESOURCE
~~~

Spring Boot also prints startup logs around these two lines. Do not confuse framework logs with the deterministic output of `CommandLineRunner`.

## 8. Option B: Complete Gradle build.gradle

For Gradle, use **settings.gradle**:

~~~groovy
rootProject.name = 'resource-split'
~~~

And **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **complete** Gradle Groovy DSL configuration for a single-module example. It preserves the Java plugin's **default sourceSets**, requiring no redeclaration of main or test resource directories.

The **Gradle Wrapper** should be checked into the repository; Gradle 8.5 supports JDK 17 and works well with Spring Boot 3.3.5. For projects using **build.gradle.kts**, translate the syntax to Kotlin DSL rather than simply renaming the file extension.

From the project root:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/resource-split-0.0.1-SNAPSHOT.jar
~~~

On Windows, use **gradlew.bat**. The **test** task verifies fixtures and the test profile; **bootJar** packages `main` outputs/resources and runtime dependencies into the executable Boot JAR.

When running the executable JAR in the default environment, the two lines printed by Java code are identical:

~~~text
app.label=PRODUCTION
main.resource=PUBLIC_RESOURCE
~~~

This consistency demonstrates that **the exact same source and resources** can be built by either tool while cleanly isolating test fixtures from the main artifact.

## 9. Verifying That the JAR Contains No Test Resources

**Do not simply trust a green test run.** After building, list the contents of the JAR directly and verify against a checklist.

### 9.1. Maven

After **./mvnw clean verify**:

~~~bash
jar tf target/resource-split-0.0.1-SNAPSHOT.jar
~~~

### 9.2. Gradle

After **./gradlew clean test bootJar**:

~~~bash
jar tf build/libs/resource-split-0.0.1-SNAPSHOT.jar
~~~

**In the entry list of the Spring Boot executable JAR**, these entries must be present:

~~~text
BOOT-INF/classes/application.properties
BOOT-INF/classes/messages/public.txt
BOOT-INF/classes/com/example/resourcesplit/ResourceSplitApplication.class
~~~

These entries **must NOT be present**:

~~~text
BOOT-INF/classes/application-test.properties
BOOT-INF/classes/fixtures/test-only.txt
BOOT-INF/classes/com/example/resourcesplit/ResourceSplitApplicationTest.class
~~~

The real JAR contains many more entries including launcher classes, metadata, and JARs under **BOOT-INF/lib/**; these are the specific entries to check. For a non-repackaged plain **jar**, layout omits the `BOOT-INF/classes` prefix, yet the **main vs. test** rule still holds.

You can pipe **jar tf** into OS-appropriate text filtering; the basic command above works whenever the JDK's **jar** tool is available. Make sure you inspect the **executable Boot JAR**, not Gradle's **-plain.jar** or an extra test JAR.

### 9.3. Inspecting Build Output Directories

Maven:

~~~text
target/classes/application.properties
target/classes/messages/public.txt
target/test-classes/application-test.properties
target/test-classes/fixtures/test-only.txt
~~~

Gradle:

~~~text
build/resources/main/application.properties
build/resources/main/messages/public.txt
build/resources/test/application-test.properties
build/resources/test/fixtures/test-only.txt
~~~

If **fixtures/test-only.txt** shows up inside **target/classes** or **build/resources/main**, inspect your source roots and copy/filter rules. Seeing it only under **target/test-classes** or **build/resources/test** is the expected state.

**Limits of this check:** confirming a specific filename is absent does not prove all sensitive data is gone. Files could be renamed, regenerated during `processResources`, or copied into the archive by a custom task. When strict control is required, audit all archive entries, task paths, and add an automated artifact verification test.

## 10. Distinguishing Test Resources, Test Dependencies, Profiles, and Packaging

Four concepts are frequently mixed up:

| Component | What does it control? | Example |
| --- | --- | --- |
| **src/test/resources** | Which files appear in **test resource outputs/classpath**. | `fixtures/test-only.txt` |
| **testImplementation** (Gradle) or **scope test** (Maven) | Which library dependencies apply only to test compile/runtime. | `spring-boot-starter-test` |
| **@ActiveProfiles("test")** | Which Spring profile is activated in the Spring Test context. | Selects `application-test.properties` |
| **bootJar/repackage** | Which main files and runtime dependencies enter the executable Boot archive. | `BOOT-INF/classes`, `BOOT-INF/lib` |

**File location**, **dependency scope**, **Spring profile**, and **packaging task** are four separate layers. Setting a dependency to test scope does not turn a file inside `src/main/resources` into a test file.

For example, keeping **application-test.yml** in **src/main/resources** can be intentional if production deployments also run a `test` staging profile. However, if that file holds credentials, secrets, or test-only fixture data, relocate it or fix the config source. Never treat filenames as a security boundary.

## 11. Using Non-Standard Source Layouts

**Prefer keeping the default layout.** Customize only when a legacy project or code-generation pipeline genuinely requires it.

### 11.1. Gradle: Adding a Directory to the Test Source Set

Suppose extra fixtures live under **src/test-extra/resources** and tests need to read them. In **build.gradle** (Groovy DSL), add:

~~~groovy
sourceSets {
    test {
        resources {
            srcDir 'src/test-extra/resources'
        }
    }
}
~~~

**srcDir** appends a resource directory to the `test` source set while keeping the default `src/test/resources`. Running **processTestResources** copies the extra resources into **build/resources/test**. **Never add `test-extra` to `sourceSets.main.resources`** if you want to keep it out of the JAR.

If you use **srcDirs = [...]** instead of **srcDir**, you replace the entire resource list. Include every directory you intend to keep so the default directory is not lost.

### 11.2. Maven: Adding a Non-Standard Test Resource Directory

In **pom.xml**, configure **build/testResources**. Example fragment for a project needing both the standard folder and an extra fixture folder:

~~~xml
<build>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
            <filtering>false</filtering>
        </testResource>
        <testResource>
            <directory>src/test-extra/resources</directory>
            <filtering>false</filtering>
        </testResource>
    </testResources>
</build>
~~~

This is an **illustrative fragment**, not a complete `pom.xml`. When merging into section 7's POM, place **testResources** inside the same **build** block as `<plugins>`; never create two sibling `<build>` blocks in one POM. Declaring `testResources` explicitly can **override** the default list, so keep `src/test/resources` if you still need it.

In Maven, **build/resources** (main) and **build/testResources** (test) are separate. Placing a fixture folder inside **build/resources** puts it into `target/classes` and risks leaking it into the artifact.

### 11.3. Custom Copy Tasks and Generated Resources

Some projects generate resources from templates or automated generators. Clearly assign the **output destination** of the generating task:

- Production files: write into main resource outputs, wire task dependencies properly, and keep output deterministic.
- Test-only files: write into test resource outputs and make the `test` task depend on the generator task.
- Never share a single output directory fed into **bootJar** if it holds both production configs and test fixtures.

In Gradle, you can register generated test resources via the `test` source set and a managed `Copy` task. In complex setups, avoid having multiple tasks write into the same output directory, which breaks Gradle incremental builds and up-to-date checks.

## 12. Resource Filtering and Sample Data

### Maven Resource Filtering

Maven Resources Plugin supports **filtering** to substitute tokens with properties when copying resources. Filtering rules for **resources** and **testResources** can be configured independently. If a test file needs test-specific substitutions, keep it in `testResources` with suitable filtering; never copy test-filtered files into `target/classes`.

For binaries, JSON containing literal placeholders, or files requiring byte-for-byte preservation, set **filtering=false**. Avoid filtering sensitive production secrets stored in the repository.

### Gradle Expand/Filter

Gradle **processResources** and **processTestResources** are distinct copy tasks. Example fragment when test-only substitution is genuinely needed:

~~~groovy
tasks.named('processTestResources') {
    filesMatching('test-settings.properties') {
        expand(testLabel: 'TEST_ONLY')
    }
}
~~~

This affects only **test-settings.properties** inside test resource sources and has no effect on main **processResources**. If resources contain no templates to expand, omit this block. Files containing `$` or braces resembling Gradle templates may need escaping with `expand`; leaving resources unfiltered is simpler whenever filtering is unnecessary.

### Preventing Sensitive Data Leaks

Separating directories alone does not protect secrets accidentally placed inside the main JAR or dependency JARs. Never commit passwords, tokens, or real user data into resources, even in test fixtures. Use secret stores/environment variables and synthetic fixtures in tests, and audit the final artifact before release.

## 13. Common Mistakes

**Mistake 1 — Placing fixtures in `src/main/resources` because tests can read them.** Tests pass, yet the fixtures are packaged into the production JAR. Move truly test-only fixtures to **src/test/resources**.

**Mistake 2 — Assuming `application-test.properties` is automatically excluded.** Profile names do not determine packaging scope. Files in **src/main/resources** stay in `main`; files in **src/test/resources** belong to `test`.

**Mistake 3 — `SpringBootTest` ignores test configuration.** Check **@ActiveProfiles("test")**, the path and spelling of **application-test.properties**, the test classpath, and overriding property sources. Simply sitting in `src/test/resources` does not activate a profile.

**Mistake 4 — Relying on test dependency scope to exclude resources from packaging.** Maven `scope=test` or Gradle `testImplementation` controls library dependencies, not resource source sets. Fix the resource directory placement.

**Mistake 5 — Pointing Gradle `sourceSets.main.resources` at `src/test/resources`.** That turns fixtures into main resources packaged by **bootJar**. Point `sourceSets.test.resources` instead.

**Mistake 6 — Pointing Maven `build/resources` at the test directory.** `process-resources` copies fixtures into `target/classes`, leaking them into the JAR. Keep `resources` and `testResources` properly separated.

**Mistake 7 — Writing `bootJar.from(sourceSets.test.output)`.** This forces test classes and fixtures into the executable JAR, bypassing the default separation. Remove the custom copy rule and verify the archive afterward.

**Mistake 8 — Using identical resource paths in `main` and `test` and relying on precedence.** Colliding paths depend on classloader/classpath ordering, which varies across plugins and IDEs. Use **application-test.properties** with explicit profiles and place fixtures under **fixtures/**.

**Mistake 9 — Treating `target/test-classes` or `build/resources/test` on disk as proof the JAR is polluted.** Those directories are normal outputs for running tests. Always inspect the entries inside the executable JAR itself.

**Mistake 10 — Running `java -jar` and accessing `src/main/resources` on the filesystem.** Packaged files live inside the archive, and the source directory may not exist in production. Read via **ClassPathResource** or **ClassLoader.getResourceAsStream**.

**Mistake 11 — Running `jar tf` on the wrong JAR.** Gradle may produce a **-plain.jar** alongside the Boot JAR. Inspect the actual deployable executable Boot JAR and check **BOOT-INF/classes/**.

**Mistake 12 — Tests pass, yet production still reads `TEST_ONLY`.** Check whether `app.label` is overridden by environment variables, CLI args, external config files, or an active profile at launch. In the example, the two default output lines assume no external overrides.

**Mistake 13 — Copying all of `build/` or `target/` into a Docker image and thinking the JAR contains tests.** The Docker build context or image may copy test output directories separately from the JAR. Copy only the intended runnable artifact in your Dockerfile; a clean JAR does not guarantee a clean image if extra folders are copied.

**Mistake 14 — Declaring custom `testResources` and dropping the standard folder.** Overriding the list can omit `src/test/resources` unless listed explicitly. Check outputs after `process-test-resources`/`processTestResources`.

**Mistake 15 — Adding `exclude '**/test/**'` during packaging and calling it separated.** Name patterns can accidentally strip runtime assets or miss differently named fixtures. Fix categorization at the source set level first, then use archive inspection to catch mistakes.

## 14. Pre-Release Verification Checklist

1. **Classify** every resource: genuinely needed by the app at runtime, or test-only?
2. **Place properly**: production resources in `src/main/resources`; test fixtures and test-only config in `src/test/resources`.
3. **Avoid cross-wiring** Maven `build/resources` with `testResources`, or Gradle `sourceSets.main` with `sourceSets.test`.
4. **Separate test dependencies**: Maven `scope=test` and Gradle `testImplementation` for JUnit/Spring Boot test tooling.
5. **Activate test profiles explicitly** with `@ActiveProfiles` or test property mechanisms; never expect directory names to enable profiles automatically.
6. **Run tests** and verify both main and test resources load on the test classpath.
7. **Package cleanly** via Maven `clean verify` or Gradle `clean test bootJar`.
8. **List the archive** with `jar tf` and confirm no test resources or test classes appear inside the executable Boot JAR.
9. **Run the artifact** with `java -jar` under expected runtime configuration; verify main resources load from the classpath and production behavior matches expectations.
10. **Audit custom tasks/Dockerfiles** to ensure they do not copy test fixtures outside the standard build layout.

## 15. Official References

- Maven — Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout
- Maven — Build Lifecycle (`process-resources`, `process-test-resources`, `test`, `package`): https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Getting Started (classpath resources for tests): https://maven.apache.org/guides/getting-started/
- Gradle — Building Java & JVM Projects (source sets, managing resources): https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Spring Boot — Gradle Plugin: Reacting to the Java Plugin / BootJar: https://docs.spring.io/spring-boot/gradle-plugin/reacting.html

**Takeaway:** **Tests can read both main resources and test resources; the executable Spring Boot JAR packages only main resources and required runtime dependencies by default.** Separating **src/main/resources** from **src/test/resources** from the start and inspecting the real JAR ensures tests have all needed data while releases never ship fixtures, test configs, or JUnit code.
