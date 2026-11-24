# Rules for Selecting Classes, Resources, and Dependencies Included in a Spring Boot Artifact

## 1. Why is packaging customization more than just renaming a JAR?

A Spring Boot application can compile successfully yet still produce a **final artifact** that is missing classes, missing configuration files, contains unnecessary dependencies, or accidentally carries internal information. Conversely, a build can package everything and turn "green", only to fail when running `java -jar` with `ClassNotFoundException`, `NoClassDefFoundError`, missing resources, or library conflicts.

Therefore, before editing `pom.xml` or `build.gradle`, define the **artifact content selection rules**:

1. **Which classes belong to production code?** Classes compiled from the main source set must go into the application; test classes/fixtures do not belong in the executable runtime.
2. **Which resources are needed on the classpath?** For example `application.properties`, templates, and static assets; files intended only for local use or secrets must not be included in the artifact.
3. **Which dependencies are needed at runtime?** Distinguish compile, runtime, test, provided, development-only, and Spring Boot packaging-specific exceptions.
4. **What kind of artifact is being packaged?** Executable Boot JAR, plain library JAR, executable WAR, container image, or native image each follow different rules.
5. **What provides the evidence?** Do not look only at `BUILD SUCCESS`; inspect the archive, manifest, resolved dependency graph, and run the actual final binary.

In a typical Spring Boot executable **JAR**, the conceptual structure is:

~~~text
packaging-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...             # Boot Loader
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/packaging/PackagingApplication.class
    │   ├── application.properties
    │   └── public/package-marker.txt
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── spring-web-<version>.jar
    │   └── ...                                      # actual runtime JARs
    ├── classpath.idx                                # optional
    └── layers.idx                                   # optional
~~~

`BOOT-INF/classes` receives the built **main output**; `BOOT-INF/lib` receives the **selected runtime libraries**. The Boot Loader at the JAR root builds the classpath and invokes `Start-Class`. Test classes and test dependencies are normally **not** included in the default Boot executable JAR.

> **Version scope:** the illustrative configurations use Java 17 and Spring Boot 3.3.13 for Maven/Gradle for easy comparison, not as advice to use one specific latest version. Newer plugins or versions may change behavior or parameters; consult the documentation for your project's exact version. The examples are practical guides; expected results should be run and verified by the learner.

## 2. Content classification: sources, build outputs, and artifacts

The best starting point is to **trace a file from its source to where it gets packaged**.

| Input type | Typical Maven | Typical Gradle | Location in executable Boot JAR |
| --- | --- | --- | --- |
| Java production source | `src/main/java` → `target/classes` | `sourceSets.main.java` → `build/classes/java/main` | `BOOT-INF/classes/<package>/...class` |
| Main resource | `src/main/resources` → `target/classes` via Resources Plugin | `sourceSets.main.resources` → `build/resources/main` via `processResources` | `BOOT-INF/classes/<resource-path>` |
| Test source | `src/test/java` → `target/test-classes` | `sourceSets.test.java` → `build/classes/java/test` | **No**, unless a custom build includes it accidentally or intentionally |
| Test resources | `src/test/resources` → `target/test-classes` | `sourceSets.test.resources` → `build/resources/test` | **No** under standard configuration |
| Runtime dependency | Maven dependency resolution and Boot repackage | Gradle `runtimeClasspath`, Boot `bootJar.classpath` | `BOOT-INF/lib/*.jar` |
| Annotation processor | Compiler/processor path | `annotationProcessor` configuration | The processor itself is **not** at runtime by default; generated main classes/resources may be packaged |
| Development tools | `spring-boot-devtools`, `spring-boot-docker-compose` | `developmentOnly` | **Normally excluded by default by the Boot plugin** |
| External project files (secrets, ops config) | Outside resources/build output | Outside source set/output | **Do not include in JAR**; inject from the deployment environment |

**"Present in the project" does not mean "present in the artifact."** Source code in `src/test` can still compile and run tests without entering `BOOT-INF/classes`; a file under `src/main/resources` can be filtered or excluded; a runtime dependency can be excluded during repackage. The actual rules must be read from the **final output**, not just by looking at repository folders.

### 2.1. Distinct content layers to control

- **Main class output:** code the app needs at runtime; membership should be decided by source set and module boundaries. Deleting a class post-compilation while another class still references it causes runtime errors.
- **Main resource output:** classpath data (message bundles, templates, static files, application config, SQL migrations, JSON mappings...). These can be filtered by path, but accidentally excluding a resource is only discovered when the feature using it is exercised.
- **Nested dependencies:** JARs required to load classes and run the application; managed via dependency declarations/scopes/configurations and constraints/BOM, then verified in packaging.
- **Boot Loader + manifest:** generated by the Spring Boot build plugin according to the layout; do not delete them manually thinking they are "not business code."
- **Layers and indexes:** `BOOT-INF/layers.idx`/`classpath.idx` affect how layers are split and classpath order under appropriate conditions, and **do not replace resource/dependency selection rules**.

### 2.2. A critical security decision

If `src/main/resources/secret.json` has already been committed with a real token, **excluding it from the JAR does not remove the token from Git history, build caches, old artifacts, or logs**. You must revoke/rotate the credential and handle the repository according to security procedures. Do not use `exclude` as a substitute for a secret manager. Ideally, keep secrets out of the source tree from the start; the artifact should contain only safe configuration and receive secrets via environment variables or a secret store at runtime.

## 3. Maven: understand scopes before customizing `repackage`

In Maven, a dependency has a `scope` and attributes such as `optional` and `exclusions`. Those values determine which classpaths it appears on, but **Spring Boot repackage has its own executable JAR packaging rules**. You must distinguish the dependency tree from the `BOOT-INF/lib` list.

| Maven declaration | Maven role | Default behavior when Spring Boot Maven Plugin `repackage` builds an executable JAR |
| --- | --- | --- |
| `compile` (default) | Used at compile time and runtime. | Considered for packaging as a runtime dependency. |
| `runtime` | Needed at runtime, not needed to compile directly. | Considered for packaging. |
| `provided` | Present at compile time; standard Maven runtime classpath assumes the container/JDK provides it. | **Still included by Boot repackage** for executable JARs according to Boot documentation; do not assume it is "excluded from the JAR." |
| `test` | Used to compile/run tests. | **Not** included in the default executable runtime JAR. |
| `system` | Library pointing to a system path; poorly reproducible. | Not included by default; `includeSystemScope` defaults to `false` and is discouraged. |
| `optional=true` on a direct dependency | Limits transitive propagation to downstream Maven consumers. | **Not an "exclude from executable JAR" directive**; Boot `repackage` may include optional dependencies (except devtools/docker-compose by default). |

**Most common pitfall:** for a Boot **executable JAR**, `<scope>provided</scope>` **does not guarantee that the library is absent from `BOOT-INF/lib`**. The Spring Boot Maven Plugin includes provided dependencies; if a specific artifact should not be distributed, clearly evaluate where the dependency is needed and apply the appropriate exclude configuration. For a **WAR**, provided/container dependencies follow separate directory rules; do not apply JAR conclusions directly to WARs.

### 3.1. Three different places that control dependencies

1. **Maven dependency declarations:** `<dependency>` with scope and exclusions changes which dependencies are resolved for the build.
2. **Dependency management/BOM:** manages versions and constraints; an entry in `<dependencyManagement>` **does not add a dependency by itself**.
3. **Spring Boot Maven Plugin `repackage`:** takes the JAR/WAR already produced by Maven and repackages it, offering options such as `excludes`, `excludeGroupIds`, `includes`, `excludeDevtools`, `excludeDockerCompose`, and `includeSystemScope`. These options affect dependency selection during repackaging, **not removing dependencies from the compile classpath or deleting source**.

When you change layer 3, you can make the artifact miss a dependency **while compilation and tests still pass**. Always run a smoke test with `java -jar` after every change.

## 4. Gradle: distinguish configurations from the classpath used to build the JAR

When using the Gradle Java plugin, dependencies are commonly declared by configuration:

| Gradle configuration | Main compile? | Main runtime/`runtimeClasspath`? | Considered when `bootJar` packages dependencies? |
| --- | --- | --- | --- |
| `implementation` | Yes. | Yes. | Yes. |
| `runtimeOnly` | Not needed at compile time. | Yes. | Yes. |
| `compileOnly` | Yes. | **No**. | **No**, unless added via another configuration. |
| `annotationProcessor` | Processor path, not a normal compile/runtime dependency. | Not by default. | Not by default; generated main classes output can enter the JAR. |
| `testImplementation` | Test compile, not main. | Not in main runtime. | Not by default. |
| `testRuntimeOnly` | Test runtime. | Not in main runtime. | Not by default. |
| `developmentOnly` (Spring Boot plugin) | For development only. | Not part of default `bootJar`. | **Excluded by default**, unless intentionally added to `bootJar.classpath`. |

The Spring Boot Gradle Plugin creates the `bootJar` task (when combined with the Java plugin). This task is a specialized `Jar` task that **packages the main source set output along with selected runtime dependencies**. `bootJar` has its own `classpath` that can be customized; in standard configuration it uses the appropriate runtime classpath and excludes `developmentOnly` by default.

**Be careful:** `compileOnly` is a configuration that **does not flow into `runtimeClasspath`**; it is not simply another name for Maven `provided` under Boot repackage. Do not map Maven scopes to Gradle one-to-one. For executable WARs, Gradle provides `providedRuntime` for servlet container libraries and the `WEB-INF/lib-provided` layout.

### 4.1. The dependency set managed by a BOM differs from the packaged dependency set

A Maven BOM or Gradle platform can declare hundreds of versions, but that does not mean every JAR in the BOM is downloaded or packaged. Only dependencies that are **declared or pulled into the graph** and belong to the runtime archive classpath enter the artifact. Therefore:

- **BOM = version management metadata**, not a "package everything" list.
- **Runtime dependency graph = key input** to see why a dependency appears.
- **Executable archive = final output to inspect**, because plugin selection and exclusions still apply.

Use Maven `dependency:tree` or Gradle `dependencies --configuration runtimeClasspath` and compare against `BOOT-INF/lib` to investigate differences rationally rather than treating every difference as an immediate bug.

## 5. Class selection rules: main source sets first, bytecode exclusion last

The first design principle should be **choosing the right modules and source sets**:

- Classes in `src/main/java` are candidates for the production artifact.
- Classes in `src/test/java` are tests, needed by the test runner but not included in the runtime JAR.
- Generated classes produced by annotation processors for **main** can enter the artifact when compiler output is packaged normally.
- Build-time plugin code or Gradle `build-logic` is not an application production class.
- A library module referenced by the app can be packaged as a **nested dependency JAR** in `BOOT-INF/lib`, rather than flattening every library class into `BOOT-INF/classes`.

### 5.1. What if a class must be omitted from the artifact?

You can configure the Maven Jar Plugin or a Gradle CopySpec to exclude entries, but you must evaluate:

1. Is that class used by business code, dependency injection, reflection, Spring component scanning, or `ServiceLoader`?
2. Does it participate in a public API or serialization/JPA mapping?
3. Does any resource or `META-INF` descriptor still point to the excluded class?
4. Does removing the class break the main entrypoint, Spring auto-configuration, or a specific profile?
5. Should the class be moved to **test sources**, a **separate module**, or a **dev-only source set** before considering post-compilation exclusion?

**Recommendation:** if a class truly does not belong in production, place it in the right source set or module from the beginning. Excluding `.class` files via path patterns at the end of the build easily creates an artifact that works on the happy path but fails when a rarely used feature invokes that class.

### 5.2. Why `mainClass` is not a class filter

Configuring `Start-Class`/`mainClass` only specifies the **startup entrypoint**. It does **not** mean Spring Boot only packages classes reachable from `main` via program analysis. A Boot JAR does not automatically strip uncalled classes like a tree shaker. Classes are packaged based on **main output and archive copy rules**, not on `main()`'s call graph.

If you want to reduce size significantly, optimize dependencies/modules and consider AOT/native image as appropriate; do not expect changing `mainClass` to remove "unused classes."

## 6. Resource selection rules: paths, filtering, and confidentiality

Resources differ from Java code in that they may not be checked by the compiler. A missing file or a file altered during `processResources` can still let the app start and then fail when the corresponding feature is used.

Examples of main resources that may be needed in the artifact:

- `application.properties`, `application.yml`, and non-secret profile-specific variants.
- `static/` (CSS/JS/images) if the app serves static content.
- `templates/` if the app renders Thymeleaf/Mustache/Freemarker.
- `messages*.properties` for localization.
- `db/migration/` for Flyway, or equivalent migration paths.
- `META-INF/services/**`, `META-INF/spring/**`, and framework metadata if used.
- Mapping/rules/schema/CSV files actually loaded by the application as classpath resources.

Things that **should not** go into main resources: private keys/passwords, developer notes, database dumps, test fixtures, tool outputs, backup configs. Any file under `src/main/resources` is normally a candidate to be copied **unless an exclude rule applies**; therefore, organize folders clearly and inspect the actual archive.

### 6.1. Resource filtering can alter behavior

In Maven, resource filtering is a phase that substitutes tokens before files enter output; in Gradle, `expand`/`filter` can be used in `processResources`. **Do not enable filtering indiscriminately across all files**:

- Spring Boot uses runtime placeholders such as `${SERVER_PORT:8080}` (or `${some.property}`). Build-time filtering must not accidentally replace placeholders that need to remain until runtime.
- Binary files can be corrupted when text filtering is applied.
- Secrets must not be "filtered" into the final archive just because Maven/Gradle has access to environment variables during the build.
- When building for multiple environments, keep a single identical artifact and pass configuration via environment variables or a secret store at runtime, instead of producing a separate JAR containing per-environment credentials.

You can use `@project.version@` with an appropriate Maven starter parent configuration for build metadata, but you must inspect the content **after processing**. In the example below, we intentionally **do not filter** resources, separating file selection from token substitution concerns.

## 7. Shared hands-on project: distinguishing included, excluded, and test-only

We use **one Spring Boot Web app** with two endpoints to verify:

- `GET /ping` returns `pong`: Java production classes and Web runtime dependencies work.
- `GET /marker` reads a classpath resource and returns `included-v1`: the resource was placed into `BOOT-INF/classes` properly.
- `internal/debug-notes.txt` exists in source resources but must **be absent from the executable artifact** per packaging rules.
- `src/test/resources/only-for-tests.txt` and `PackagingApplicationTest.class` belong only to the test phase and must **be absent from the runtime JAR**.

Structure:

~~~text
packaging-demo/
├── pom.xml                         # CHOOSE Maven if using Maven
├── settings.gradle                 # CHOOSE Gradle if using Gradle
├── build.gradle                    # Do not configure both tools at the same time
├── src/
│   ├── main/
│   │   ├── java/com/example/packaging/PackagingApplication.java
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── public/package-marker.txt
│   │       └── internal/debug-notes.txt
│   └── test/
│       ├── java/com/example/packaging/PackagingApplicationTest.java
│       └── resources/only-for-tests.txt
└── (Maven Wrapper OR Gradle Wrapper, created by the project)
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=packaging-demo
server.port=8080
~~~

File `src/main/resources/public/package-marker.txt`:

~~~text
included-v1
~~~

File `src/main/resources/internal/debug-notes.txt`:

~~~text
This local diagnostic resource must not be packaged.
~~~

File `src/test/resources/only-for-tests.txt`:

~~~text
test-fixture-only
~~~

All of these are **harmless dummy contents**, not real credentials. The goal is to clearly observe inclusion and exclusion.

### 7.1. Java 17 main class

`src/main/java/com/example/packaging/PackagingApplication.java`:

~~~java
package com.example.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PackagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/marker")
    public String marker() throws IOException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        try (InputStream in = loader.getResourceAsStream("public/package-marker.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing public/package-marker.txt");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }
}
~~~

Notes:

- `@SpringBootApplication` and `main()` create the Spring Boot context, and `@RestController` exposes HTTP endpoints.
- `marker()` uses a **classpath resource InputStream**, not `new File("BOOT-INF/classes/...")`. A resource inside an executable JAR is not a regular file on the filesystem.
- `readAllBytes()` and `StandardCharsets.UTF_8` are available in Java 17. Calling `trim()` avoids depending on a trailing newline in the resource file.
- If the resource is accidentally excluded, the `/marker` endpoint fails with `IllegalStateException`; this is a very practical check.
- This class runs **inside a Maven/Gradle Spring Boot project with dependencies**, not as a standalone Java program compiled with `javac PackagingApplication.java` without a classpath.

### 7.2. JUnit + MockMvc test

`src/test/java/com/example/packaging/PackagingApplicationTest.java`:

~~~java
package com.example.packaging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PackagingApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void mainClassAndMarkerResourceWork() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));

        mvc.perform(get("/marker"))
           .andExpect(status().isOk())
           .andExpect(content().string("included-v1"));
    }
}
~~~

This is **test source**: it exists for verification, not as a runtime component. MockMvc tests request mappings through the Spring test context, not `java -jar`. Passing tests confirm the resource is on the **test runtime classpath**, but you still need to inspect the **final archive** and run the real binary to confirm correct packaging.

## 8. Complete Maven example: exclude main resources by path, keep needed runtime deps

The `pom.xml` example below uses the Spring Boot starter parent and declares an explicit **resource copy rule**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <!-- Intentionally disable filtering in this example to avoid altering resource contents -->
                <filtering>false</filtering>
                <excludes>
                    <exclude>internal/**</exclude>
                    <exclude>**/*.pem</exclude>
                </excludes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Explanation:**

1. `maven-resources-plugin` processes `src/main/resources` before packaging. The `<resources>` block tells it to copy resources from source, **excluding `internal/**` and `**/*.pem`**. `public/package-marker.txt` and `application.properties` are still copied.
2. `<filtering>false</filtering>` is intentional so Spring `${...}` placeholders are not accidentally altered. If your project requires resource filtering, configure the **appropriate resources/filtering semantics** rather than copying this config blindly.
3. The Boot parent manages dependency versions and plugin defaults. Declaring `spring-boot-maven-plugin` binds the `repackage` goal to the appropriate lifecycle phase.
4. `spring-boot-starter-test` has `test` scope so it does not become a nested runtime JAR of the application.
5. Exclusions under **`<build><resources>`** are **path/file rules**. They are **not** equivalent to Maven dependency `<exclusions>` or Spring Boot Maven Plugin `<excludes>`.

**Important:** when you write `<build><resources>` yourself, you may **override resource processing/filtering defaults** inherited from the starter parent. This lesson disables filtering for transparency; a system using `@project.version@` or generating configs at build time needs to preserve or reproduce the required rules before adopting this.

### 8.1. Maven build commands and inspection steps

~~~bash
# From the Maven project root with Wrapper (macOS/Linux)
./mvnw -version
./mvnw clean verify

# Inspect main resources after processing and main classes after compilation
# (use ls/cat or file explorer on your respective OS)
ls -l target/classes/
ls -l target/classes/public/

# Inspect executable JAR
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Expected (if the build succeeds and files match the lesson):

~~~text
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/public/package-marker.txt
BOOT-INF/lib/<actual-runtime-libraries>.jar
~~~

Must **not** be present:

~~~text
BOOT-INF/classes/internal/debug-notes.txt
BOOT-INF/classes/com/example/packaging/PackagingApplicationTest.class
BOOT-INF/classes/only-for-tests.txt
~~~

`PackagingApplicationTest.class` normally resides in `target/test-classes` in build output, **not inside the executable JAR**. Because `BOOT-INF/classes/only-for-tests.txt` does not exist by default, if a test resource were accidentally included in the JAR, it must also be caught by grepping/searching filenames across the entire archive rather than checking only a single path.

### 8.2. Maven: exclude a dependency from the repackaged archive

This is an **illustrative configuration snippet** inside `spring-boot-maven-plugin`; the coordinates `com.example:unused-agent` are a hypothetical example to explain syntax, **not a real dependency in the runnable POM in section 8**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.example</groupId>
                <artifactId>unused-agent</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

This option tells the Spring Boot Plugin **not to include the specified artifact** in the executable archive, and goals sharing dependency filtering such as `run` may be affected. It **does not remove** the dependency from `pom.xml` or from the Maven compile classpath. You must confirm that the application **does not need classes/resources from that artifact at runtime**; if it does, excluding it can turn a green build into a `NoClassDefFoundError`.

The `excludeGroupIds` option is broader (excluding an entire groupId) and dangerous if it accidentally drops needed runtime dependencies. `includes` is a plugin artifact allowlist, **not a way to whitelist resource files**. Do not use `<includes>` on the Boot Plugin to filter `src/main/resources`.

### 8.3. Maven: difference between dependency exclusions and plugin exclusions

Transitive dependency exclusion snippet:

~~~xml
<!-- Syntax illustration only; coordinates must be replaced with real dependencies -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>business-sdk</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>unneeded-transport</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

`<exclusions>` on a dependency alters the **transitive dependency resolution graph** for that dependency; Boot Plugin `<excludes>` decides **what goes into the already-built artifact**. They operate at different points and do not replace each other. If a dependency is unused in compile, test, and runtime alike, the cleanest approach is to **remove its declaration or adjust the dependency graph at the source**.

## 9. Complete Gradle example: filter resource output, choose the right `runtimeClasspath`

Use the same Java source/resources/test from section 7, replacing the POM with Gradle files. This is an **independent build choice**; you do not need to maintain two build systems at once.

`settings.gradle`:

~~~groovy
rootProject.name = 'packaging-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('processResources') {
    // Affects only main resources being copied, without touching test resources.
    exclude 'internal/**'
    exclude '**/*.pem'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Explanation:**

- `java` creates `main`/`test` source sets, `processResources`, `compileJava`, `test`, and the JAR task. `org.springframework.boot` adds `bootJar`.
- `io.spring.dependency-management` together with the Spring Boot Plugin manages versions for starters and test libraries. An alternative is Gradle's native `platform("org.springframework.boot:spring-boot-dependencies:...")`; choose one consistent dependency management model.
- `processResources` is a **Copy task** that produces the main resource output. The two `exclude` rules filter paths before resources reach `build/resources/main`, and then `bootJar` takes that output into `BOOT-INF/classes`.
- `testImplementation` and `testRuntimeOnly` serve tests and must not be treated as production runtime deps just because JUnit tests pass.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` provides the JUnit Platform launcher for Gradle's test runtime suitable for the example.
- `spring-boot-devtools` is not declared, so the example has no development-only dependency; if present, the Boot Gradle Plugin excludes `developmentOnly` from the executable archive by default.

You can use `sourceSets.main.resources.exclude` if you want resource exclusion rules applied **directly at the main resource source set** across multiple tasks. The example above uses `processResources` to highlight which phase determines resource output contents; if a project has custom tasks reading source resources directly or `bootRun.sourceResources`, re-check them because those paths may bypass the same filtering.

### 9.1. Gradle build and verification

~~~bash
./gradlew --version
./gradlew clean build

# View source set runtime graph
./gradlew dependencies --configuration runtimeClasspath

# Inspect executable JAR contents and built library files
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Under standard configuration, `bootJar` creates the file without a classifier, while the `jar` task may create `packaging-demo-0.0.1-SNAPSHOT-plain.jar`. Do not use a wildcard that accidentally picks `*-plain.jar` for runtime smoke testing. If you have customized `archiveFileName`/classifier, take the actual name from the task output or `build/libs`.

### 9.2. Gradle: scope selection and dependency exclusion

An example of **transitive exclusion declaration** (snippet, hypothetical coordinates):

~~~groovy
dependencies {
    implementation('com.example:business-sdk:1.0.0') {
        exclude group: 'com.example', module: 'unneeded-transport'
    }
}
~~~

`exclude group/module` applies to the declared dependency edge and affects the resolution graph; the artifact may still reach the classpath via a **different** dependency path. Use `dependencyInsight` when you need to know why an artifact still appears. Do not treat it as a directive to "delete a file from the ZIP after packaging."

When you need to change what `bootJar` packages, you can configure the **`bootJar.classpath` task property** with an intentional `FileCollection`/resolvable configuration. However, replacing `classpath` carelessly can strip out Spring Framework, starters, or project dependencies: this is an **advanced** configuration that must be based on an analyzed `runtimeClasspath` and verified on the executable JAR afterward. Never copy an empty `bootJar { classpath = files() }` just to shrink a JAR.

### 9.3. `bootJar`, `jar`, and copy/exclude rules

- `bootJar` creates the Spring Boot executable JAR containing the loader, `BOOT-INF/classes`, and `BOOT-INF/lib`.
- `jar` creates the plain/library JAR. Unless customized, the Boot Gradle Plugin typically applies the `plain` classifier to separate outputs.
- `tasks.named('processResources') { exclude ... }` affects resources entering main output, so it can affect **both the plain JAR and `bootJar`**.
- `tasks.named('bootJar') { ... }` accepts some standard packaging options from Gradle `Jar`/`CopySpec`, but given the path layout built by `BootJar`, do not assume a glob matching the source path will always hit the final entry. Always verify with actual `jar tf`.

If you want to exclude a resource from **only one artifact** while keeping it on the development classpath, consider a staging/copy task with explicit inputs/outputs and artifact tests rather than applying broad excludes across all main output unpredictably.

## 10. Spring Boot special cases: devtools, Docker Compose, optional/provided

### 10.1. Maven `spring-boot-devtools`

For example, if added in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Do not infer that "`optional=true` causes it to be excluded from the executable JAR" based on general Maven rules. The **Spring Boot Maven Plugin** actively excludes `spring-boot-devtools` by default via `excludeDevtools=true`; `spring-boot-docker-compose` is likewise excluded by default via `excludeDockerCompose=true` in supported versions. If you inadvertently set `excludeDevtools=false`, you change the package contents. Check the intent and risk before doing so.

### 10.2. Gradle `developmentOnly`

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

The Boot Gradle Plugin **does not package** dependencies in `developmentOnly` into the executable JAR/WAR by default. If a team intentionally adds them via `bootJar.classpath`, the package contents will differ from the default and require careful review. Do not let DevTools or development tooling run accidentally in production.

### 10.3. Maven `provided` differs from Gradle `compileOnly`

Suppose a dependency is intended only for compile time:

- Maven `provided` in a **Boot executable JAR** can still be packaged by the plugin by default.
- Gradle `compileOnly` sits outside normal `runtimeClasspath`, so it is not packaged by `bootJar` by default.
- For an **executable WAR**, Spring Boot uses a different layout: `WEB-INF/classes`, `WEB-INF/lib`, and for eligible servlet container dependencies, `WEB-INF/lib-provided`. Gradle `providedRuntime` is a better fit than `compileOnly` when packaging an executable/deployable WAR.

This is why you should not use a superficial "scope mapping" table to migrate Maven to Gradle. You must understand **artifact type + task/goal + actual classpath**.

### 10.4. Packaged runtime dependencies can differ from "used at startup" dependencies

A library might only be loaded when a user triggers a rare endpoint, runs a scheduled job, parses an Excel file, or enables a Spring profile. If you exclude it simply because a `/ping` smoke test passes, failures may only surface after deployment. Therefore, before excluding a dependency, analyze code paths, optional features, Spring auto-configuration, `ServiceLoader`, reflection, and appropriate coverage/integration test reports.

## 11. Resource filtering and per-environment config: avoid accidentally packaging secrets

Suppose a Spring Boot file contains:

~~~properties
server.port=${SERVER_PORT:8080}
spring.application.name=packaging-demo
~~~

Spring Boot resolves placeholders at **runtime**; you do not need to rebuild the JAR just to change `SERVER_PORT`. However, if Maven/Gradle filtering is used carelessly, `${SERVER_PORT:8080}` may be treated as a build-time template and altered unexpectedly.

### 11.1. If you genuinely need build metadata

For example, if you want the app to know the artifact version, you can put an `@project.version@` token in a dedicated resource and configure filtering with the proper delimiter. In the Maven starter parent, certain filtering defaults are configured to reduce conflicts with Spring placeholders. If you override `<resources>` completely as in section 8, those defaults may no longer apply: document and re-verify them.

In Gradle, a targeted snippet for a template file:

~~~groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(projectVersion: project.version.toString())
    }
}
~~~

Use this snippet only if `src/main/resources/build-info.properties` is a template containing `${projectVersion}` for the build; it must **not** be treated as a requirement to apply `expand` across all resources. With Spring placeholders, restrict filtering to target files and inspect the contents under `BOOT-INF/classes` after packaging.

### 11.2. Do prod/test/dev environments really need three separate JARs?

**No.** In many architectures, you should package **one immutable executable artifact** and pass profiles, endpoints, credentials, and feature flags via the runtime environment. For example:

~~~bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

This only illustrates how to select a profile; it does **not** mean production secrets belong inside the archive. `application-prod.yml` can live in the JAR if it contains only non-sensitive configuration, while secrets are injected externally.

If you genuinely need distinct distributions per customer or license, define explicitly named package variants with separate source sets/task inputs and test each variant; do not mix multiple exclude rules driven by untracked build-machine environment state.

## 12. Distinguishing resource exclusion, dependency exclusion, and class exclusion

A common mistake is using one kind of `exclude` to solve the wrong layer of problem.

| What do you want to change? | Maven: primary place | Gradle: primary place | What not to do |
| --- | --- | --- | --- |
| Omit `internal/debug-notes.txt` from the artifact | `<build><resources><resource><excludes>` / Resources Plugin | `processResources.exclude` or source set resource rules | Use Boot Plugin dependency excludes to filter paths. |
| Remove an unwanted transitive dependency | `<dependency><exclusions>` | `dependency { exclude group/module }` | Manually delete nested JARs after the build. |
| Exclude a dependency from Boot repackaging (intentionally) | `spring-boot-maven-plugin<configuration><excludes>` | Adjust dependency graph or `bootJar.classpath` with verification | Modify source set class exclusions if this is a library JAR. |
| Exclude devtools from the executable archive | Boot Plugin default `excludeDevtools=true` | `developmentOnly` excluded by default | Put DevTools into production alongside runtime libraries unnecessarily. |
| Block test classes from the artifact | Place classes in `src/test/java` | Use `sourceSets.test` | Put tests in main and exclude them with fragile globs. |
| Omit unused production classes | Split module/source set or refactor source design | Split module/source set or refactor source design | Delete `.class` files post-compile while other classes still reference them. |
| Change only the main entrypoint | Boot Maven Plugin `mainClass` | `bootJar.mainClass` or `springBoot.mainClass` | Confuse with class-tree include/exclude. |
| Choose executable WAR instead of JAR | Maven `packaging=war` + Boot plugin + servlet dep scope | Gradle `war` + Boot `bootWar` + `providedRuntime` | Apply JAR's `BOOT-INF` layout assumptions to a WAR. |

**The right question to ask before editing:** "Do I need to change the **dependency graph**, the **main output**, or **only archive copy selection**?" Then pick the exact build phase and verify the output after that phase.

## 13. QA workflow: evidence from source to runtime

Using the exact Java file and resources from section 7, choose Maven or Gradle, and follow these steps in order:

### 13.1. Step 1 — build and tests must actually run

Maven:

~~~bash
./mvnw clean verify
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

Check the reports:

- Maven: `target/surefire-reports/` must show that `mainClassAndMarkerResourceWork` ran and passed.
- Gradle: `build/test-results/test/` and `build/reports/tests/test/` record JUnit results.
- If you see `0 tests` or `NO-SOURCE`, do not conclude tests passed merely because the build succeeded.

### 13.2. Step 2 — select the right artifact and inspect entries

Maven:

~~~bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Gradle:

~~~bash
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Expected: `META-INF/MANIFEST.MF`, Boot Loader, `BOOT-INF/classes/com/example/packaging/PackagingApplication.class`, `BOOT-INF/classes/public/package-marker.txt`, `BOOT-INF/classes/application.properties`, and the runtime `BOOT-INF/lib/*.jar` files.

**Verify entries that must be absent:**

~~~text
BOOT-INF/classes/internal/debug-notes.txt
BOOT-INF/classes/only-for-tests.txt
BOOT-INF/classes/com/example/packaging/PackagingApplicationTest.class
BOOT-INF/lib/junit-jupiter-<version>.jar
BOOT-INF/lib/spring-boot-devtools-<version>.jar
~~~

For JUnit/DevTools, do not check only exact filenames with assumed versions; scan actual artifact names using filters or by reviewing entries. Test files only appear in test output if a real project uses default source sets.

### 13.3. Step 3 — positive and negative CLI filtering

macOS/Linux example with the Maven JAR:

~~~bash
JAR=target/packaging-demo-0.0.1-SNAPSHOT.jar

# Required entries
jar tf "$JAR" | grep '^BOOT-INF/classes/com/example/packaging/PackagingApplication.class$'
jar tf "$JAR" | grep '^BOOT-INF/classes/public/package-marker.txt$'
jar tf "$JAR" | grep '^BOOT-INF/lib/'

# Entries that must be excluded
jar tf "$JAR" | grep -E '(^BOOT-INF/classes/internal/|PackagingApplicationTest.class|only-for-tests.txt|/junit-jupiter-|spring-boot-devtools-)'
~~~

In the final command, **printing no lines** (with `grep` typically returning exit code 1) is the **expected** result for the example, not a Java application error. In a CI pipeline, write explicit exit-code assertions rather than relying on visual inspection.

A small check script for presence/absence (macOS/Linux, requires `grep`):

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/packaging-demo-0.0.1-SNAPSHOT.jar"
LIST="$(jar tf "$JAR")"

# Production class and resource present
printf '%s\n' "$LIST" | grep -q '^BOOT-INF/classes/com/example/packaging/PackagingApplication.class$'
printf '%s\n' "$LIST" | grep -q '^BOOT-INF/classes/public/package-marker.txt$'

# No internal resources, test classes/fixtures, or DevTools
if printf '%s\n' "$LIST" | grep -Eq '(^BOOT-INF/classes/internal/|PackagingApplicationTest.class|only-for-tests.txt|spring-boot-devtools-)'; then
    echo "FAIL: unwanted file found in executable JAR" >&2
    exit 1
fi

echo "PASS: required entries included, forbidden entries excluded"
~~~

**Expected stdout when the script passes:**

~~~text
PASS: required entries included, forbidden entries excluded
~~~

If an unwanted file is found, the script prints an error line to **stderr** and exits with code 1. This script checks only a few representative conditions; it does not prove the entire dependency graph is safe or that no secrets remain in the archive.

For Gradle, change the `JAR` variable to `build/libs/packaging-demo-0.0.1-SNAPSHOT.jar`. On Windows PowerShell, replace `grep` with `Select-String` or use a dedicated Java test; do not run a raw Bash script in PowerShell and assume the project is broken.

### 13.4. Step 4 — read the packaged resource inside the archive

With `unzip`:

~~~bash
unzip -p "$JAR" BOOT-INF/classes/public/package-marker.txt
unzip -p "$JAR" BOOT-INF/classes/application.properties
~~~

`unzip -p` extracts an entry to stdout without unpacking the entire archive. The path is the **classpath location inside the executable JAR**, not a filesystem path next to the JAR. If `unzip` is unavailable, use `jar xf` in a **separate inspection directory** and read the extracted files; do not extract the whole archive over your source tree.

Expected output of the marker file:

~~~text
included-v1
~~~

### 13.5. Step 5 — run the actual packaged binary

Stop any `spring-boot:run`/`bootRun` process using the same port. Maven:

~~~bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Or Gradle:

~~~bash
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

In another terminal, once the app is ready:

~~~bash
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/marker
~~~

Expect HTTP 200 with bodies `pong` and `included-v1`, respectively. Startup messages, HTTP headers, and latency may vary by JDK, web server, and OS; do **not** treat illustrative output as a live run log. This is the check that verifies **artifact contents + classloading + HTTP runtime** simultaneously.

## 14. Multi-module projects: avoid packaging the wrong module or dropping internal dependencies

A repository with `core`, `api`, and `app` modules typically needs:

- `core`/`api` as **library modules**, producing plain JARs and declaring appropriate public/internal APIs.
- `app` as the **Spring Boot application module**, with `main()`, `bootJar`, or `repackage`.
- The dependency from `app` to `core` typically becomes a **nested JAR in `BOOT-INF/lib`**, rather than automatically flattening into `BOOT-INF/classes` unless specially configured.
- Do not apply the Boot plugin or `repackage` to every library module that has no main class.

Maven can use `<modules>` to aggregate, child `<parent>` to inherit, and `dependencyManagement` to align versions. Gradle uses `include('core','app')` in settings and `implementation project(':core')` in `app`. Either way, **inspect resolved project dependencies** after building.

### 14.1. Dangerous exclusions in multi-module builds

A Boot Maven Plugin configuration `<excludeGroupIds>com.example</excludeGroupIds>` can accidentally exclude **internal application library modules** sharing that groupId. Similarly in Gradle, stripping all internal project dependencies from `bootJar.classpath` might let the app start until a rarely touched feature invokes `core` and fails.

Use specific criteria (which artifact/module to drop, why, and who owns verification) instead of overly broad group or path globs.

### 14.2. Fat JAR does not mean flattening every class to the root

A Spring Boot executable JAR uses nested dependencies in `BOOT-INF/lib`. A shadow/shaded JAR typically merges dependency classes as root entries; the two approaches have different resource merging and classloader rules. Do not assume every class from an internal dependency must sit directly in `BOOT-INF/classes`. In a Boot JAR, a class in `core.jar` is loaded by the classloader from the **nested `core.jar`**.

## 15. Stronger customization: when should and shouldn't you use it?

Some real-world advanced needs:

### 15.1. Packaging artifacts for a specific feature set

If a feature requires heavy dependencies (PDF engine, native bindings, cloud client) that not every instance needs, you can split the feature into a **separate module** or explicitly named distribution/variant. Do not exclude a few nested JARs via untested patterns; you must prove the application no longer references them. Runtime feature toggles do not stop the JVM from needing classes when the feature is actually enabled.

### 15.2. License, notice, and SBOM resources

For compliance, verify license notices, dependency metadata, SBOMs, and provenance per organizational standards. Do not strip license files or `META-INF/services` to save a few KB: they may be legal obligations or required for `ServiceLoader` to function.

### 15.3. Layered JARs and container caching

`BOOT-INF/layers.idx` can be used to split dependencies, snapshot dependencies, the loader, and app resources into layers. **Changing layer assignment does not remove content from the JAR**; its primary purpose is organizing content to optimize Docker/buildpacks caching. To reduce footprint, you must change actual content selection or runtimes, not merely move a library to another layer.

### 15.4. WAR and `providedRuntime`

If the deliverable is an executable/deployable WAR instead of a JAR:

- Maven uses `packaging=war` with its own scope and container semantics.
- Gradle `war` + Spring Boot `bootWar`; `providedRuntime` fits servlet container dependencies so they land in `WEB-INF/lib-provided` when external container compatibility is needed.
- WARs use `WEB-INF/classes`, `WEB-INF/lib`, and optionally `WEB-INF/lib-provided`—**not** the `BOOT-INF` paths from JAR assertions.

Always write archive assertions **according to the artifact type**; do not treat a WAR lacking `BOOT-INF/classes` as an error.

### 15.5. Native executables, OCI images, and AOT are not Boot JAR clones

GraalVM native images, Spring Boot `bootBuildImage`/`build-image`, and AOT mechanisms have different inputs and outputs. Do not apply `jar tf` checks to a native executable binary; instead use binary/image inspection, SBOMs, behavioral tests, runtime dependencies, and appropriate policies. This lesson evaluates **Spring Boot executable JARs**.

## 16. Diagnosing common failures

| Symptom | Common cause | Root cause analysis and fix |
| --- | --- | --- |
| `/marker` fails when running the JAR even though tests pass. | Marker exists on test classpath/dev output but was excluded from packaged main resources or another copy task. | Compare `target/classes`/`build/resources/main` with `BOOT-INF/classes`; check build filtering/excludes. |
| `BOOT-INF/classes/internal/debug-notes.txt` is still present. | Exclude rule missed the folder, source comes from elsewhere, or a custom copy task added it. | Check relative path from resource root; verify Gradle `processResources` or Maven `<resources>` applies to the right module. |
| Java classes in `src/test/java` appear in the artifact. | Custom source sets/output packaging or a task copying test output too. | Restore source set boundaries; check task inputs of `jar`/`bootJar` or Jar Plugin. |
| Test dependencies (JUnit/Mockito) appear in `BOOT-INF/lib`. | Declared as production dependencies or manually added to `bootJar` classpath. | Check Maven scope/Gradle configuration and archive classpath. |
| Maven `provided` dependency still appears in the Boot JAR. | Spring Boot Maven Plugin `repackage` includes `provided` by default. | This may be expected behavior; if unneeded, configure a tested exclusion rather than guessing from scope. |
| Maven `optional=true` dependency is still packaged. | `optional` affects transitivity, not packaging exclusion; Boot may include it. | Use Boot Plugin `excludes` for artifacts to omit; DevTools has its own exclusion. |
| Gradle `compileOnly` library is missing at runtime. | Not part of `runtimeClasspath`. | If genuinely needed at runtime, switch to `implementation` or `runtimeOnly` per contract. |
| Gradle `developmentOnly` lib is missing from `BOOT-INF/lib`. | Boot Gradle Plugin excludes `developmentOnly` by default. | Usually intentional; do not put DevTools into production unnecessarily. |
| Build passes but `NoClassDefFoundError` occurs when enabling a profile. | Dependency was excluded or only the happy path was tested. | Read stack trace, dependency graph, `BOOT-INF/lib`, and test that profile. |
| `ClassNotFoundException` for main class. | Wrong `mainClass`/`Start-Class`, or class missing from `BOOT-INF/classes`. | Check manifest, `repackage`/`bootJar` task, source path, and compile output. |
| Classpath resource cannot be opened with `new File(...)`. | Entry is inside the archive, not a filesystem file. | Use `getResourceAsStream`/Spring `Resource`; extract separately if a library strictly requires a physical file. |
| Packaged `*-plain.jar` by mistake. | Selected artifact using a wildcard or outdated name. | Check manifest + `BOOT-INF` and run `java -jar` on the true executable archive. |
| `spring-boot:run`/`bootRun` passes but JAR fails. | Development classpath differs from packaged output. | Compare main output, `runtimeClasspath`, filtering, plugin excludes, and packaged smoke test. |
| `application.yml` had placeholders replaced. | Build-time resource filtering collided with Spring runtime placeholders. | Scope filtering to specific files/delimiters and inspect packaged contents. |
| Overly broad exclude removed metadata. | Deleted `META-INF/spring/**` or `META-INF/services/**`. | Do not exclude framework resources manually; check usage, restore, and run integration tests. |
| Secret file is absent from JAR yet still exposed. | Already committed or present in caches/logs/old artifacts. | Revoke credentials, audit distribution channels, and follow security incident response. |
| Assumed using a BOM means all libraries are packaged. | BOM manages versions only; it does not add dependencies. | Inspect actual dependency declarations and resolved runtime graph. |
| Fails on another machine at runtime. | Different JDK, profile, external config/secrets/ports, or runtime environment. | Record version/JAR hash and verify in a production-like environment. |

### Layered diagnostic order

1. **Source:** is the file in main or test? Where is it generated from?
2. **Build output:** did compiler and resource processing generate/copy the expected files?
3. **Resolved graph:** does the dependency have the right scope/configuration and version?
4. **Packaging selection:** what classes, resources, and deps did the Boot plugin/task select?
5. **Archive:** what do `jar tf` and the manifest show?
6. **Runtime:** does `java -jar` load classes/resources and perform real behavior properly?

Do not immediately edit the manifest or move every dependency to `implementation` at the first runtime error; that can hide scope mistakes and bloat the artifact.

## 17. Final lab and completion criteria

### Lab A — prove resource inclusion/exclusion

1. Create the source tree with `PackagingApplication.java`, `PackagingApplicationTest.java`, two main resources, and one test resource as in section 7.
2. Build with Maven or Gradle per section 8/9, ensuring `clean verify` or `clean build` runs real tests.
3. Verify `BOOT-INF/classes/public/package-marker.txt` exists.
4. Verify `BOOT-INF/classes/internal/debug-notes.txt` does not exist.
5. Verify `PackagingApplicationTest.class` and `only-for-tests.txt` do not appear anywhere in the executable runtime JAR.
6. Run the real binary and call `GET /marker`; the response body must be `included-v1`.

### Lab B — prove dependency selection

1. Run Maven `dependency:tree` or Gradle `dependencies --configuration runtimeClasspath`.
2. List nested entries under `BOOT-INF/lib`.
3. Pick one actual runtime dependency and explain whether it came from a starter or a direct dependency.
4. Confirm test-only JUnit/Mockito are not packaged, and DevTools is not packaged by default if DevTools is added under the right configuration.
5. For Maven, explain why `provided`/`optional` does not mean excluded from repackage; for Gradle, explain `compileOnly`/`developmentOnly`.
6. Describe a case where excluding a transitive dependency on a dependency declaration differs from excluding during repackaging.

### Lab C — test a controlled change

Rename `public/package-marker.txt` to a different path **without changing Java code**, then run the build/tests. Expect `mainClassAndMarkerResourceWork` or packaged `/marker` to fail because the resource path in code no longer matches. Restore the resource path, perform a clean build, and prove both tests and the executable runtime pass.

This exercise only illustrates **resource verification**; never introduce intentional failures on a release branch. For dependency exclusions, experiment only on a learning branch with test coverage over features using that dependency and a clear rollback.

### Evaluation checklist

- [ ] Can explain the three content sources of an executable JAR: main output, runtime deps, Spring Boot Loader/manifest.
- [ ] Distinguishes `src/main/java`, `src/main/resources`, `src/test/java`, and `src/test/resources`.
- [ ] Uses Maven `<build><resources>` or Gradle `processResources` properly to filter a resource by path.
- [ ] Does not confuse resource excludes with Maven/Gradle dependency exclusions.
- [ ] Understands that a BOM manages versions rather than automatically adding JARs to the runtime graph.
- [ ] Correctly states Spring Boot Maven `provided`/`optional` behavior and Boot Maven `excludeDevtools`/`excludeDockerCompose`.
- [ ] Correctly states Gradle `implementation`, `runtimeOnly`, `compileOnly`, `testImplementation`, and `developmentOnly`.
- [ ] Does not accidentally exclude `META-INF/spring/**`, `META-INF/services/**`, or dependencies loaded via reflection.
- [ ] Does not treat `mainClass` as a class tree-shaking/exclusion mechanism.
- [ ] Inspects the true executable Boot JAR, not `*-plain.jar` or `*.jar.original`.
- [ ] Has test reports plus positive and negative archive entry assertions.
- [ ] Has a `java -jar` smoke test proving artifact code and resources work.
- [ ] Does not ship secrets in the archive; knows that `exclude` does not erase secrets from Git history.
- [ ] Knows how to write separate assertions for JAR/WAR/container/native artifacts.

**Completion criteria:** the learner can articulate decisions for **selecting classes/resources/dependencies** at the right build layer, produce a controlled executable JAR, prove via entry listings that the marker is **included** and debug/test-only files are **excluded**, explain why runtime dependencies are present or absent, and run the **actual packaged binary**. Every conclusion must be backed by evidence from real builds/reports/archives/runtime runs, not guessed from `pom.xml` or `build.gradle`.

## Official references

- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Resources Plugin — Filtering and Inclusion/Exclusion](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Gradle — Building Java and JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)

**Remember:** **source sets + resource processing + resolved runtime dependencies + packaging plugin selection** together determine the final artifact's contents. Avoid using post-packaging excludes as a quick fix; designing proper scopes/modules and inspecting the **actual JAR file** is far more sustainable.