# Keeping a Separate Library Artifact When a Project Also Produces an Executable Artifact

## 1. Problem and goals

A Spring Boot project may need **two deliverables from the same source tree**: a library JAR for other applications to use as a dependency, and an executable JAR with the Spring Boot launcher to run via `java -jar`. Although both end in `.jar`, their internal layout and usage contracts differ. If Maven replaces the main JAR with a Boot executable JAR by default, downstream modules declaring a normal dependency may fail to import classes. If Gradle configures the same output filename for `jar` and `bootJar`, one task can overwrite the other's artifact.

This lesson shows how to **preserve an unclassified library artifact** while producing a separate **executable artifact with classifier `exec`**, and how to verify both consumption and publication. For larger projects, it also explains when to split into `core` and `app` modules instead of maintaining both roles in one module.

After this lesson, you will be able to:

1. Compare a plain Java JAR with a Spring Boot executable JAR by layout and classpath.
2. Configure Maven `spring-boot:repackage` with `classifier=exec` and understand `attach`.
3. Configure Gradle `jar` and `bootJar` with distinct classifiers, and create a Maven publication containing the primary library and supplemental `exec` artifact.
4. Write a runnable example using Java 17, Spring Boot 4.1.2, Maven, and Gradle.
5. Compile a standalone Java consumer **using only the ordinary JAR**, then run the HTTP service from the `exec` JAR to verify both contracts independently.
6. Identify errors related to metadata, classifiers, plugin inheritance, dependency coupling, and multi-module setups.
7. Define QA gates for build artifacts, consumers, and release repositories.

**Context:** *Packaging Customization* in Spring Boot Build Tooling Packaging. Examples use Java 17, Spring Boot 4.1.2, compatible Maven, or a Gradle version supported by the Boot plugin. The sample artifact name is `dual-artifact-demo:1.0.0`.

## 2. Why can't a single Boot JAR act as both executable and library?

### Plain JAR used as a library

In an ordinary JAR, classes sit at paths matching their package names:

~~~text
dual-artifact-demo-1.0.0.jar
├── META-INF/MANIFEST.MF
└── dev/example/dual/
    ├── DualArtifactApplication.class
    └── api/PublicGreeting.class
~~~

Another program can import `dev.example.dual.api.PublicGreeting` when this JAR is placed on the compile classpath. A library JAR **does not require** an executable `Main-Class` or bundled runtime dependencies. Its dependency graph comes from its POM or Gradle Module Metadata when published.

### Executable Spring Boot JAR

When using Maven `spring-boot:repackage` or Gradle `bootJar`, the default layout of an executable JAR is:

~~~text
dual-artifact-demo-1.0.0-exec.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── dev/example/dual/
    │       ├── DualArtifactApplication.class
    │       └── api/PublicGreeting.class
    └── lib/
        ├── spring-boot-...jar
        └── ...
~~~

The Spring Boot launcher constructs a specialized classpath from `BOOT-INF/classes` and nested JARs in `BOOT-INF/lib` for `java -jar`. However, standard Java compilers and classloaders **do not treat `BOOT-INF/classes` as the root package path** when an executable JAR is placed on a library classpath. Consequently, a downstream project will report `package ... does not exist` even though the class exists inside the executable JAR.

| Aspect | Plain library JAR | Boot executable JAR |
| --- | --- | --- |
| Class path | `dev/example/.../*.class` | `BOOT-INF/classes/dev/example/.../*.class` |
| Runtime dependencies | Resolved via POM/module metadata | Normally nested under `BOOT-INF/lib` |
| Entry point | Optional | Boot launcher and `Start-Class` |
| Consumers | `javac`, compilers, Maven/Gradle dependency graph | JVM `java -jar`, deployment platforms |
| Proper verification | Compile/run consumer from classpath | Launch app and run smoke tests |
| Interchangeable? | No | No |

**Principle:** an ordinary JAR is a **classpath contract for consumers**; an executable JAR is a **runtime contract for deployment**. Classifiers distinguish the artifacts, while packaging itself produces the two structures.

## 3. Three architectural options

**Option A — One module, two archives.** Sharing `groupId:artifactId:version`, the ordinary JAR keeps the **unclassified** coordinates while the executable JAR uses classifier `exec`. Minimal project restructuring, synchronized versions, suitable when maintaining an app with a small reusable API.

**Option B — Two modules `core` and `app`.** `core` holds API/logic and emits only a library JAR; `app` depends on `core` and builds the Boot executable. Cleaner boundaries; consumers do not accidentally pull in the application's web/database dependencies. Usually the best choice for multiple downstream consumers.

**Option C — Two repositories or release streams.** Used when the public library and service have different ownership, compatibility guarantees, security boundaries, or release cadences. In exchange, version and dependency management are heavier. Do not jump to Option C just because you want an `-exec.jar` file.

~~~text
A — Single-module dual artifact
src/main/java --> compile --> plain.jar        (library)
                        \--> Boot repackage   (exec.jar)

B — Multi-module
core/src --> core.jar (library)
             |
             v
app/src + core.jar --> bootJar/repackage --> app.jar (executable)
~~~

**Important note:** emitting two files in the same module **does not automatically split the dependency graph**. A consumer needing only pure Java API classes may still inherit dependency metadata for the whole Spring Boot module. Split modules once that coupling becomes significant.

## 4. Maven: by default `repackage` replaces the main artifact

When a Maven module uses `jar` packaging, the `package` phase runs `maven-jar-plugin:jar` first, creating an ordinary JAR. `spring-boot:repackage` then turns that source archive into an executable archive. If **no classifier is configured**, the plugin replaces the **main artifact** with the executable JAR by default; the original is typically saved locally as `*.jar.original`.

~~~text
Default:
target/dual-artifact-demo-1.0.0.jar          -> executable
target/dual-artifact-demo-1.0.0.jar.original -> pre-repackage JAR
~~~

When `mvn install` or `mvn deploy` runs with default `attach=true`, the **main artifact** is the executable JAR. That breaks other projects needing the ordinary JAR at unclassified coordinates. `.jar.original` exists only in the build directory and is **not** a supplementary artifact automatically published as a library.

### Configuring classifier `exec`

Keep the ordinary JAR at the primary coordinates and create an additional executable JAR:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**This configuration is for use with `spring-boot-starter-parent`.** The parent already defines an execution with ID `repackage`; the child customizes that **same ID** to merge configuration instead of adding another execution that runs `repackage` twice.

Output:

~~~text
target/dual-artifact-demo-1.0.0.jar       -> plain library JAR
target/dual-artifact-demo-1.0.0-exec.jar  -> executable Boot JAR
~~~

Two corresponding Maven coordinates:

~~~text
dev.example:dual-artifact-demo:jar:1.0.0
dev.example:dual-artifact-demo:jar:exec:1.0.0
~~~

The first has no classifier; the second uses `exec`. **Classifier is part of artifact identity, not a new `artifactId`.**

### Role of `attach`

- `attach=true` (default): with `classifier=exec`, the executable is attached **alongside** the ordinary JAR for `install`/`deploy`.
- `attach=false`: the executable is still created locally, yet not attached for `install`/`deploy`. Use only when the pipeline publishes the library while delivering the executable through another channel.
- `skip=true`: skips `repackage`, so no executable JAR is produced by that goal.
- `layout=NONE`: omits the Boot bootstrap launcher; unsuitable if you need standard `java -jar` execution.

Distinguish **files generated in `target`** from **artifacts actually attached/published**. A green build does not guarantee a remote repository received both.

## 5. Complete Maven example, Java 17 and Spring Boot 4.1.2

### Project structure

~~~text
dual-artifact-demo/
├── pom.xml
├── src/main/java/dev/example/dual/
│   ├── DualArtifactApplication.java
│   └── api/PublicGreeting.java
├── src/test/java/dev/example/dual/PublicGreetingTest.java
└── consumer/
    └── ConsumerMain.java
~~~

The `consumer` directory simulates a separate program **outside** Maven's main source set. That way, compiling the consumer genuinely tests the ordinary JAR output rather than accidentally reading classes from project sources.

### `pom.xml`

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

    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <classifier>exec</classifier>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This POM does not need to repeat `<goal>repackage</goal>` because the starter parent already provides that execution. The classifier is placed **inside that exact execution** to preserve the original JAR as the main artifact.

### Library API — `src/main/java/dev/example/dual/api/PublicGreeting.java`

~~~java
package dev.example.dual.api;

public final class PublicGreeting {
    private PublicGreeting() {
    }

    public static String text() {
        return "LIBRARY_OK";
    }
}
~~~

This is a pure Java API requiring no Spring to consume. The aim is a classpath contract verifiable via `javac` and `java` without needing web framework dependencies in the consumer demo.

### Application — `src/main/java/dev/example/dual/DualArtifactApplication.java`

~~~java
package dev.example.dual;

import dev.example.dual.api.PublicGreeting;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DualArtifactApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualArtifactApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting() {
        return PublicGreeting.text();
    }
}
~~~

The Spring Boot app uses the same API class and returns its value over HTTP. In Spring Boot 4.1.2, `spring-boot-starter-webmvc` provides the dependencies needed for MVC and auto-configures the servlet web server.

### Unit test — `src/test/java/dev/example/dual/PublicGreetingTest.java`

~~~java
package dev.example.dual;

import dev.example.dual.api.PublicGreeting;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublicGreetingTest {
    @Test
    void returnsExpectedLibraryValue() {
        assertEquals("LIBRARY_OK", PublicGreeting.text());
    }
}
~~~

This test checks Java logic, yet does **not** prove the library archive places classes at package root. Hence we still need the consumer test and JAR inspection in the following sections.

### Build

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Expected output:

~~~text
target/
├── classes/...
├── surefire-reports/...
├── dual-artifact-demo-1.0.0.jar
└── dual-artifact-demo-1.0.0-exec.jar
~~~

With `repackage` using a classifier, do **not** expect a `.jar.original` file. The ordinary JAR and executable JAR are two distinct artifacts, not an old backup of one another. Check Maven logs to see `jar:jar` run before `spring-boot:repackage`.

## 6. Inspecting both artifacts independently

### 6.1. Inspect archive layout

~~~bash
jar tf target/dual-artifact-demo-1.0.0.jar
jar tf target/dual-artifact-demo-1.0.0-exec.jar
~~~

The ordinary JAR must contain:

~~~text
dev/example/dual/api/PublicGreeting.class
dev/example/dual/DualArtifactApplication.class
~~~

The executable JAR must contain:

~~~text
BOOT-INF/classes/dev/example/dual/api/PublicGreeting.class
BOOT-INF/classes/dev/example/dual/DualArtifactApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

The plain JAR needs no `Main-Class`. The executable JAR defaults to a manifest with the Boot launcher in `Main-Class` and the application class in `Start-Class`. `jar tf` proves entry presence, not consumer compilation or app startup.

### 6.2. Java consumer — `consumer/ConsumerMain.java`

~~~java
package dev.consumer;

import dev.example.dual.api.PublicGreeting;

public class ConsumerMain {
    public static void main(String[] args) {
        System.out.println("CONSUMER=" + PublicGreeting.text());
    }
}
~~~

**Linux/macOS** from project root, after `mvn clean verify`:

~~~bash
mkdir -p target/consumer-classes
javac -cp target/dual-artifact-demo-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:target/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Exact stdout:**

~~~text
CONSUMER=LIBRARY_OK
~~~

On Windows PowerShell, the classpath separator is a semicolon:

~~~powershell
New-Item -ItemType Directory -Force target\consumer-classes | Out-Null
javac -cp target\dual-artifact-demo-1.0.0.jar -d target\consumer-classes consumer\ConsumerMain.java
java -cp "target\consumer-classes;target\dual-artifact-demo-1.0.0.jar" dev.consumer.ConsumerMain
~~~

If `javac` cannot import `PublicGreeting` from the ordinary JAR, verify package name, version/classifier, and `jar tf` output. Never pass `target/classes` on `-cp` in the consumer test, as that masks ordinary JAR packaging bugs.

**Counter-check:** swapping `-cp` to `-exec.jar` in `javac` stops the standard compiler from seeing classes at the classpath root as expected. That reflects the Boot executable JAR's layout, not missing classes.

### 6.3. Test the executable via HTTP

In terminal one:

~~~bash
java -jar target/dual-artifact-demo-1.0.0-exec.jar --server.port=18080
~~~

In terminal two, once the server has started:

~~~bash
curl -fsS http://127.0.0.1:18080/greeting
~~~

**Exact HTTP response body:**

~~~text
LIBRARY_OK
~~~

The app does not print this string to stdout; it is the **HTTP response body**. Do not claim the whole console output is `LIBRARY_OK`, as Spring Boot emits logs too. Stop the server with `Ctrl+C` after testing.

Both checks serve distinct roles: the **consumer test** proves the ordinary JAR works as a library; the **HTTP smoke test** proves the executable JAR runs with its runtime dependencies.

## 7. Maven without starter parent: binding the goal explicitly

If a module inherits a corporate parent or only imports the `spring-boot-dependencies` BOM, remember that a BOM import manages only **dependency versions**—it does not bring in the Boot starter parent's executions. You must specify the Boot Maven Plugin version and bind `repackage` to the `package` phase.

This is a **fragment for `<build><plugins>`**, not a complete POM:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The BOM is imported separately under `<dependencyManagement>` with `<type>pom</type>` and `<scope>import</scope>`. Compiler, Surefire, Jar Plugin, and Java release target also need versions/config because starter parent defaults are no longer inherited.

Run `mvn help:effective-pom` to inspect executions. If a corporate parent already defines `repackage`, the child must merge/customize the matching execution ID to avoid duplicate runs.

**Source selection pitfall with classifiers:** When a source JAR already carries the **same `exec` classifier**, Boot `repackage` may pick it as the source archive instead of the ordinary main JAR. Avoid having `maven-jar-plugin` accidentally emit another `-exec.jar`. When multiple goals share the `package` phase, declare the Jar Plugin before the Boot Plugin so the source archive is built first.

## 8. Maven `install`/`deploy` and coordinates of the two artifacts

With `classifier=exec` and default `attach=true`:

~~~bash
mvn clean install
~~~

The local Maven repository normally holds:

~~~text
~/.m2/repository/dev/example/dual-artifact-demo/1.0.0/
├── dual-artifact-demo-1.0.0.pom
├── dual-artifact-demo-1.0.0.jar
└── dual-artifact-demo-1.0.0-exec.jar
~~~

A **downstream Maven consumer** depends on the unclassified ordinary artifact:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Adding `<classifier>exec</classifier>` would pull the executable artifact, which **should not be used** as a normal compile dependency. A consumer needing only the public library API should never try reading `BOOT-INF/classes` with custom hacks.

`mvn install` installs only locally; `mvn deploy` publishes to a remote repository using `distributionManagement` and credentials. Running `mvn package` or `mvn verify` does not publish either artifact. After publishing, verify **files, classifiers, and metadata** in the actual repository.

In projects where the executable is only used to build a container image, you can set `attach=false` and publish only the ordinary JAR, yet **do not** do that if deployment pipelines download the `exec` classifier from the repository. Clarify the distribution policy upfront.

## 9. Gradle: `jar` and `bootJar` have separate outputs and classifiers

When applying the Spring Boot Gradle Plugin with the Java plugin:

- `jar` builds an ordinary JAR with classes at root package paths.
- `bootJar` builds an executable Spring Boot archive with `BOOT-INF/classes` and `BOOT-INF/lib`.
- By default in the Boot Gradle Plugin, when `bootJar` is configured, `jar` gets classifier `plain` so outputs do not overwrite each other:

~~~text
build/libs/
├── dual-artifact-demo-1.0.0.jar        # bootJar executable
└── dual-artifact-demo-1.0.0-plain.jar  # ordinary JAR
~~~

To make the **library artifact unclassified** and give the executable the `exec` variant as in Maven, explicitly set:

~~~groovy
tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
}
~~~

Desired output:

~~~text
build/libs/
├── dual-artifact-demo-1.0.0.jar       # ordinary library
└── dual-artifact-demo-1.0.0-exec.jar  # Boot executable
~~~

Note that `jar` and `bootJar` are two distinct tasks. **Do not disable `jar`** when the ordinary JAR is a deliverable. Conversely, seeing two `.jar` files in `build/libs` does not prove a publication includes both; publishing is a separate step.

## 10. Complete Gradle Groovy DSL example

Reuse `PublicGreeting`, `DualArtifactApplication`, `PublicGreetingTest`, and `consumer/ConsumerMain.java` from sections 5–6. For Gradle, create:

**`settings.gradle`**

~~~groovy
rootProject.name = 'dual-artifact-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot' version '4.1.2'
    id 'maven-publish'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
    mainClass = 'dev.example.dual.DualArtifactApplication'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact tasks.named('bootJar')
        }
    }
}
~~~

**Explanation:**

- `java-library` creates the Java component and ordinary `jar`. This is a clean choice when a module publishes an API.
- The Spring Boot Gradle Plugin creates `bootJar`, wired into `assemble` when the Java plugin is present.
- The BOM is brought in via Gradle native `platform` to manage starter versions; using `api platform` propagates appropriate constraints through Java component metadata. In real projects, evaluate how much dependency/BOM exposure consumers should receive.
- `jar.archiveClassifier=''` makes the ordinary JAR unclassified.
- `bootJar.archiveClassifier='exec'` classifies the executable JAR.
- `maven-publish` creates publication `mavenJava`. `from components.java` publishes the ordinary Java library component as the primary artifact; `artifact tasks.named('bootJar')` attaches the executable JAR as a supplemental artifact.
- Avoid adding a second publication with indistinguishable extension and classifier, which causes duplicates/collisions or ambiguity over the primary artifact.
- `maven-publish` can generate Gradle Module Metadata alongside the Maven POM. To ensure downstream consumers resolve the right variant, verify actual resolved metadata across both Maven and Gradle consumers upon release.

### Run the Gradle build

With a compatible Gradle Wrapper in the project:

~~~bash
./gradlew clean build
jar tf build/libs/dual-artifact-demo-1.0.0.jar
jar tf build/libs/dual-artifact-demo-1.0.0-exec.jar
~~~

The ordinary JAR must contain `dev/example/dual/api/PublicGreeting.class` at root; the executable JAR must hold that class under `BOOT-INF/classes`. `build` runs Java verification tasks in the graph, and the Boot plugin wires `bootJar` into `assemble`. Running `./gradlew bootJar` alone **does not guarantee unit tests ran**.

### Consumer test with Gradle outputs

~~~bash
mkdir -p build/consumer-classes
javac -cp build/libs/dual-artifact-demo-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:build/libs/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Exact stdout:** `CONSUMER=LIBRARY_OK`.

### Run the executable and test HTTP

~~~bash
java -jar build/libs/dual-artifact-demo-1.0.0-exec.jar --server.port=18080
~~~

In another terminal:

~~~bash
curl -fsS http://127.0.0.1:18080/greeting
~~~

Exact HTTP body is `LIBRARY_OK`.

### Local publish

~~~bash
./gradlew publishToMavenLocal
~~~

This publishes the configured publication artifacts **into the local Maven repository**. Check both `.jar` and `-exec.jar` plus metadata in that repo; do not assume any remote registry was updated. Publishing remotely requires configuring repositories and credentials in `publishing.repositories` per organizational policy.

## 11. Dependency and API coupling considerations

Keeping library and executable in one module does not split their dependency metadata. Because `dual-artifact-demo` has `spring-boot-starter-webmvc` as a runtime dependency, publishing the ordinary JAR from the same module can cause consumers to resolve web/framework dependencies even though `PublicGreeting` does not use Spring.

This is **not a classifier bug**. Classifiers separate artifact files, not POM/module dependency graphs. Mitigations:

- Keep the **public API** small and avoid exposing Spring/Web/DB types if the library does not intend to depend on them.
- Control Maven scopes and `dependencyManagement` carefully; never arbitrarily mark a dependency `provided` just to shrink the graph if the executable needs it at runtime.
- With Gradle `java-library`, separate `api` from `implementation`. Put dependencies in `api` only when their types appear in the public API; audit publication metadata.
- When multiple consumers exist or the library needs an independent release cadence, split `core` and `app` modules.
- Document API compatibility policies (binary/source), versioning, deprecations, and artifact coordinates so consumers are not forced onto unexpected service upgrades.

## 12. Multi-module: the cleaner approach for larger projects

~~~text
root/
├── greeting-core/           -> plain JAR, library API
│   └── dev.example.core.GreetingService
└── greeting-app/            -> executable Boot JAR
    └── depends on greeting-core
~~~

**Maven:** Root uses packaging `pom` with modules `greeting-core` and `greeting-app`. The core module needs only `jar:jar` without enabling `repackage`; the app module applies `spring-boot-maven-plugin` and holds `@SpringBootApplication`.

Root `pom.xml` fragment:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>greeting-core</module>
    <module>greeting-app</module>
</modules>
~~~

Dependency in app `pom.xml` fragment:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

**Gradle:** `settings.gradle`:

~~~groovy
rootProject.name = 'dual-artifact-platform'
include 'greeting-core', 'greeting-app'
~~~

App `build.gradle` fragment:

~~~groovy
dependencies {
    implementation project(':greeting-core')
}
~~~

These fragments illustrate **module wiring**, not complete build configurations; repositories, BOMs, plugin versions, and Java toolchains still need proper setup. `greeting-core` applies `java-library`; `greeting-app` applies the Boot Gradle Plugin. Library consumers depend on **`greeting-core`**, never `greeting-app`.

**Pitfall to avoid:** never bind Boot `repackage` on a `pom`-packaged root or inherit it indiscriminately across all child library modules; doing so can turn libraries into executable archives or cause the root module to fail looking for a source JAR to repackage.

## 13. Distinguishing publishing from consumption

| Action | Maven | Gradle | Meaning |
| --- | --- | --- | --- |
| Build ordinary JAR | Default `jar:jar` in `package` | `jar` | Library artifact |
| Build exec JAR | `spring-boot:repackage` classifier `exec` | `bootJar` classifier `exec` | Runnable artifact |
| Run tests | `mvn verify` | `./gradlew build` | According to configured goals/tasks |
| Install to local repo | `mvn install` | `publishToMavenLocal` | Test consumers on build machine |
| Publish remotely | `mvn deploy` | `publish` with repository config | Release artifacts elsewhere |
| Library consumer | No classifier | Java library coordinates/variant | Normal classpath consumption |
| Deploy executable | Classifier `exec` or explicit app file | `bootJar` output | `java -jar` / container |

**Never treat `mvn package` or `./gradlew build` as proof that artifacts were published.** Build outputs sit in `target`/`build/libs`; publication is an explicit subsequent step.

Standard Maven consumer:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Adding `<classifier>exec</classifier>` selects the executable artifact, which should not be used to compile normal Java consumers. In Gradle, a consumer can declare `implementation 'dev.example:dual-artifact-demo:1.0.0'` but should verify Gradle Module Metadata/variants when a repository publishes multiple artifacts and custom variants. Whenever an API is stable, a standalone library module avoids long-term ambiguity.

## 14. Common pitfalls

| Symptom | Common cause | Check to run |
| --- | --- | --- |
| Consumer fails to import classes | Used Boot executable instead of ordinary JAR | `jar tf`: classes must sit at package root |
| `java -jar` on plain JAR fails | Missing Boot launcher or runtime deps | Run the actual `-exec.jar` |
| Maven creates `.jar.original` with no ordinary library published | No classifier; `repackage` replaced main artifact | Set classifier `exec`, check `attach` |
| Maven Boot plugin runs twice | Starter parent already defines ID `repackage`; child added a different ID | Reuse inherited ID and inspect effective POM |
| Maven exec not published | `attach=false` or execution skipped | Check config and install/deploy logs |
| Maven picks wrong archive as source | An existing artifact already had classifier `exec` | Check Jar Plugin executions and `package` phase order |
| Gradle outputs collide on path | `jar` and `bootJar` share name/classifier | Set `jar=''`, `bootJar='exec'` |
| Gradle builds only exec JAR | `jar` task disabled or omitted from graph | Re-enable `jar`; inspect `assemble` and outputs |
| Gradle builds 2 JARs yet publishes 1 | Publication lacks `artifact tasks.named('bootJar')` | Configure `maven-publish` and inspect local repo |
| Publication fails with duplicate artifact | Both JARs share extension/classifier in publication | Assign distinct classifiers |
| App and consumer out of sync on version | Pipeline built two artifacts from different commits/versions | Build in one job/commit and compare checksums |
| Consumer pulls unnecessary dependencies | One module acts as both service and library | Extract `core`; check Maven scopes/Gradle `api` vs `implementation` |
| CI counts 2 files yet still fails | One file is `.original`, sources JAR, or plain JAR misnamed as exec | Verify class layout and run real consumer/app checks |
| Core module gets repackaged | Boot plugin inherited too broadly | Activate Boot plugin only in application modules |

**Debugging order:** check **GAV/classifier → actual files → archive layout → consumer compilation → executable startup → repository metadata** in sequence. Do not swap JDKs over a classifier mistake.

## 15. Quality gates for both artifacts

**Gate A — Library:** plain JAR exists; `PublicGreeting.class` is at Java package root; consumer `javac -cp` compiles cleanly; `ConsumerMain` prints exactly `CONSUMER=LIBRARY_OK`.

**Gate B — Executable:** `exec` JAR exists; contains `BOOT-INF/classes`, `BOOT-INF/lib`, and Boot launcher; `java -jar` starts; HTTP `GET /greeting` returns 200 with body `LIBRARY_OK`.

**Gate C — Build lineage:** required unit tests are actually discovered and run; both artifacts come from the same source commit/version; no task/goal overwrites another's output; archive checksums and manifests are recorded if policy requires.

**Gate D — Publication:** unclassified ordinary JAR and classified `exec` JAR are published per policy; a downstream consumer resolves from the repository and compiles cleanly; deployment selects the exact `exec` artifact.

**Basic Maven QA commands on Linux/macOS:**

~~~bash
mvn clean verify
jar tf target/dual-artifact-demo-1.0.0.jar
jar tf target/dual-artifact-demo-1.0.0-exec.jar
mkdir -p target/consumer-classes
javac -cp target/dual-artifact-demo-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:target/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Basic Gradle QA commands:**

~~~bash
./gradlew clean build
jar tf build/libs/dual-artifact-demo-1.0.0.jar
jar tf build/libs/dual-artifact-demo-1.0.0-exec.jar
mkdir -p build/consumer-classes
javac -cp build/libs/dual-artifact-demo-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:build/libs/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Note:** `jar tf` only prints entries without asserting them; in CI, assert exact entries and fail if missing. The HTTP executable smoke test requires managing a background server process, timeouts, cleanup, and an unused port; in the demo you run it in terminal one and `curl` from terminal two.

Never equate `BUILD SUCCESS` with satisfying the library/executable contract. Maven/Gradle only guarantee configured goals/tasks executed, not that the right deliverable was designated as the default library artifact.

## 16. Exercises with answers

**Exercise 1.** Why might a JAR in `target` contain `PublicGreeting.class` yet still fail to compile a Maven consumer?

*Answer:* the class may reside under `BOOT-INF/classes` in a Boot executable; standard compilers expect it at the package root of an ordinary JAR.

**Exercise 2.** When Maven starter parent already configures `repackage`, should you create a new execution with a different ID to add classifier `exec`?

*Answer:* No. Customize the execution sharing the `repackage` ID to prevent duplicate execution.

**Exercise 3.** With `classifier=exec`, when is the executable published by Maven?

*Answer:* When the goal executes with `attach=true` (the default), it is attached and included when `install`/`deploy` run.

**Exercise 4.** Why is `.jar.original` not a substitute for the main library artifact?

*Answer:* It is primarily a local pre-repackage backup, lacking the identity, classifier, and publication status of the ordinary main library JAR.

**Exercise 5.** Gradle's Boot plugin may give `jar` the `plain` classifier by default. To make the library unclassified and the executable classified, what do you configure?

*Answer:* `jar.archiveClassifier=''` and `bootJar.archiveClassifier='exec'`.

**Exercise 6.** Does `./gradlew build` creating two JARs prove the Maven repository received both?

*Answer:* No. You need `maven-publish`, a publication with `components.java` and the `bootJar` artifact, and then verify `publishToMavenLocal` or the actual remote repository.

**Exercise 7.** API classes compiled fine from the ordinary JAR, yet the JVM running `exec` throws a classpath error. Is it necessarily a classifier problem?

*Answer:* Possibly not—inspect executable packaging, manifest, nested dependencies, runtime JDK, and config; the consumer test proves only the ordinary JAR.

**Exercise 8.** Does keeping two JARs in the same module automatically remove Spring Web dependencies for consumers?

*Answer:* No. Dependency metadata still belongs to the module. Splitting `core`/`app` separates dependency and API contracts cleanly.

## 17. Final checklist

- [ ] **Library artifact** name and contract are agreed upon.
- [ ] **Executable artifact** name and contract are agreed upon.
- [ ] Ordinary JAR has classes at package root path.
- [ ] Executable JAR has Boot loader, `BOOT-INF/classes`, and `BOOT-INF/lib`.
- [ ] Maven starter parent: customized execution ID `repackage` with classifier `exec`.
- [ ] Maven without starter parent: pinned plugin version, bound goal to `package`, set classifier `exec`.
- [ ] No secondary source artifact shares the same classifier and misleads `repackage`.
- [ ] `attach` matches publication policy.
- [ ] Gradle `jar` remains enabled with empty classifier; `bootJar` carries classifier `exec`.
- [ ] Gradle `maven-publish` publishes the Java component and `exec` artifact if both are required.
- [ ] Consumer genuinely compiles and runs against the ordinary JAR.
- [ ] Application actually boots via `java -jar` and passes HTTP smoke tests.
- [ ] Both outputs come from the same commit/version with no overwrites.
- [ ] Evaluated splitting `core`/`app` if many consumers or heavy dependency coupling exist.
- [ ] Inspected local/remote repository post-publish, not just `target`/`build/libs`.

**Conclusion:** **do not use a Spring Boot executable JAR as a library JAR**. When a project must produce both, Maven uses `repackage` with classifier `exec` and Gradle uses `jar`/`bootJar` with distinct classifiers; both require explicit publication config and two separate verification tests.

## 18. Official documentation

1. [Spring Boot Maven Plugin — Packaging Executable Archives; Custom Classifier](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot Maven Plugin — Repackage Parameters: classifier, attach, layout](https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot:repackage)
3. [Spring Boot Gradle Plugin — Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
4. [Spring Boot Gradle Plugin — Publishing Your Application](https://docs.spring.io/spring-boot/gradle-plugin/publishing.html)
5. [Spring Boot Executable JAR Format — Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
6. [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
7. [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
8. [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
9. [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
10. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)