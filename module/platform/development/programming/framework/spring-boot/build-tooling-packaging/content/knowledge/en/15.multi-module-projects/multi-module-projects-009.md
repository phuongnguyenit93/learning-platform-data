# Publishing POM or Gradle Module Metadata That Accurately Reflects Dependencies

## 1. The Problem in a Multi-Module Spring Boot Project

In a Spring Boot repository with multiple modules, development teams often use a **project dependency** so an application depends on an internal library. However, once the library is published to a Maven repository, external consumers **can no longer read the `build.gradle` or `pom.xml` in the original source repository**. They receive only the published artifact files, such as:

~~~text
com.example:core:1.0.0
├── core-1.0.0.jar
├── core-1.0.0.pom
└── core-1.0.0.module    # when Gradle publishes Gradle Module Metadata
~~~

The **JAR** holds bytecode/resources. The **POM** and **Gradle Module Metadata (GMM)** tell Maven/Gradle which dependencies that module needs, which versions, whether they go onto the compile or runtime classpath, and in Gradle's case, additional variants/attributes.

A library can work cleanly inside a multi-project build yet have **broken metadata after publishing**. Consequences:

- Consumers fail to compile because a class exposed in the library's **public API** is missing.
- Consumers compile cleanly yet fail at runtime due to a missing **implementation dependency** or JDBC driver.
- Test libraries leak into production applications.
- Maven consumers and Gradle consumers resolve different dependency graphs.
- The POM references a **parent POM/BOM that is absent from the repository**.
- The pipeline publishes a **Spring Boot executable JAR** instead of a standard library JAR, so consumers cannot locate classes.

**Goal:** publish a **plain Java library JAR** alongside metadata that accurately describes API, implementation, runtime, and versions; distinguish this from packaging a **Spring Boot executable app**. This lesson demonstrates both Gradle Java Library + `maven-publish` and Maven multi-module, and verifies the result using an independent consumer.

**Sample versions:** Java 17, Spring Boot 3.3.5, Gradle 8.5, Maven 3.9.x, library version 1.0.0. These versions are pinned so the example is reproducible; they do not represent the latest versions.

## 2. Distinguishing JAR, Maven POM, and Gradle Module Metadata

### 2.1. Library JAR vs Spring Boot Executable JAR

An ordinary library JAR has classes at standard Java classpath paths:

~~~text
core-1.0.0.jar
└── com/example/core/CatalogFormatter.class
~~~

It does not bundle all of Guava, Commons Lang, and JDBC drivers inside itself. **Consumers must receive the transitive dependency graph from metadata**.

A Spring Boot executable JAR typically has the layout:

~~~text
app-1.0.0.jar
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/app/CatalogApplication.class
    └── lib/...
~~~

The second JAR is meant to be launched with **java -jar**. However, app classes sit under **BOOT-INF/classes**, not at the classpath root of a library JAR. **Never use a Boot JAR as a compile dependency for another module.** In this lesson's architecture, **core publishes a library**, whereas **app only packages for deployment**.

### 2.2. Maven POM and Dependency Scopes

A Maven POM is an XML file describing a module by **groupId:artifactId:version** along with dependencies, parent, `dependencyManagement`, and related metadata. A POM can declare:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
        <version>33.3.1-jre</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This is a **fragment**, not a complete POM. Maven has these key scopes:

| Maven Scope | When Used as a Dependency |
| --- | --- |
| **compile** | Used at compile and runtime; transitive. |
| **runtime** | Not required at compile time, yet used at runtime; transitive accordingly. |
| **provided** | Needed at compile/test time, supplied by the JDK or runtime container; not pulled in as a normal runtime dependency for consumers. |
| **test** | For the module's own tests; not propagated as a product dependency to consumers. |
| **import** | Only inside `dependencyManagement` with `type` `pom` to import a BOM; not a runtime JAR. |

A pure POM lacks Gradle's full distinction between **apiElements** and **runtimeElements**. A `compile` dependency in Maven may actually be an internal implementation detail, yet Maven has no **implementation** configuration separating public API the way Gradle Java Library does.

### 2.3. Gradle Module Metadata and Variants

**Gradle Module Metadata** is a JSON **.module** file. It describes variants with **attributes, capabilities, dependencies, dependency constraints, and artifacts** alongside the module version.

Conceptual view of a Java library:

~~~text
core-1.0.0.module
├── apiElements
│   ├── usage = java-api
│   ├── artifact = core-1.0.0.jar
│   └── dependencies needed for the consumer's compiler
└── runtimeElements
    ├── usage = java-runtime
    ├── artifact = core-1.0.0.jar
    └── dependencies needed to run the library
~~~

This is a **logical diagram**, not literal full JSON. Gradle consumers use attributes to pick the matching variant. This expresses compile/runtime boundaries more precisely than a generic POM.

**Gradle `maven-publish`** usually publishes **both POM and .module side by side** with the library JAR. Maven reads the POM, while Gradle can prefer `.module` when the repository and metadata sources allow. Publishing `.module` does not break Maven's ability to consume the POM.

## 3. Right Dependency Model to Publish

We build **core** with three distinct needs:

1. **Commons Lang** provides **Pair<String,String>**, which appears in a public method signature. Consumers must see Commons Lang when compiling. Gradle declares **api**.
2. **Guava** provides **CharMatcher**, used solely inside a method body; consumers do not need to import Guava at compile time. Gradle declares **implementation**. Yet runtime still requires Guava.
3. **H2 JDBC driver** is needed only at runtime when calling **java.sql.DriverManager**, without importing H2 classes directly in source. Gradle declares **runtimeOnly**.
4. **JUnit Jupiter** is only for testing the library. Gradle declares **testImplementation**; Maven declares **scope test**.

Contract table for **Gradle `java-library`**:

| Direct Dependency | `core` Configuration | Consumer API/Compile | Consumer Runtime |
| --- | --- | --- | --- |
| commons-lang3 3.14.0 | **api** | Yes | Yes |
| guava 33.3.1-jre | **implementation** | Not exposed as API by `core` | Yes |
| h2 2.3.232 | **runtimeOnly** | No | Yes |
| junit-jupiter 5.11.3 | **testImplementation** | No | No |
| junit-platform-launcher 1.11.3 | **testRuntimeOnly** | No | No |

**Note:** "No" means this configuration **does not supply** the dependency to that classpath; it does not rule out that another dependency might happen to bring the library in. Do not conclude `core` published wrong metadata from a graph influenced by other transitive paths.

### 3.1. Why Does the Public ABI Determine `api`?

The **ABI (Application Binary Interface)** includes any types that a consumer's compiler must understand when calling public/protected methods, using superclasses/interfaces, public fields, or public annotations. If a public method returns **Pair**, while Commons Lang is declared as `implementation`, `core` compiles fine yet consumers lack the `Pair` type on their compile classpath per the contract.

Conversely, Guava's `CharMatcher` appears only inside the method body. Declaring it as **api** leaks implementation details, increases coupling, and can cause consumers to rely on transitive libraries accidentally.

### 3.2. Why Must Runtime Dependencies Still Be Published?

**Hiding Guava from the compile API** does not mean **dropping Guava from runtime**. When `core` executes `CharMatcher`, the class must still exist. Likewise, JDBC URL **jdbc:h2:mem:** requires the H2 driver to load at runtime. POM/GMM must publish runtime dependencies even when consumer compilers never import those classes.

## 4. Two-Module Sample Structure

~~~text
publisher/
├── settings.gradle           # Gradle option
├── pom.xml                   # Maven option
├── core/
│   ├── build.gradle          # Gradle or Maven pom.xml
│   └── src/
│       ├── main/java/com/example/core/CatalogFormatter.java
│       └── test/java/com/example/core/CatalogFormatterTest.java
└── app/
    ├── build.gradle          # Gradle or Maven pom.xml
    └── src/main/java/com/example/app/CatalogApplication.java
~~~

**core** is the library module published at **com.example:core:1.0.0**. **app** is a Spring Boot executable app depending on `core`. When practicing, pick **Gradle or Maven** and create the corresponding build files; there is no need to maintain both build systems simultaneously.

## 5. Three Complete Java 17 Files for Both Maven and Gradle

### 5.1. `core/CatalogFormatter.java`

File **core/src/main/java/com/example/core/CatalogFormatter.java**:

~~~java
package com.example.core;

import com.google.common.base.CharMatcher;
import org.apache.commons.lang3.tuple.Pair;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Locale;

public final class CatalogFormatter {
    private CatalogFormatter() {
    }

    public static Pair<String, String> describe(String raw) {
        String normalized = CharMatcher.whitespace()
                .trimFrom(raw)
                .toUpperCase(Locale.ROOT);
        return Pair.of("normalized", normalized);
    }

    public static boolean canOpenEmbeddedDb() throws SQLException {
        try (Connection connection =
                DriverManager.getConnection("jdbc:h2:mem:catalog")) {
            return !connection.isClosed();
        }
    }
}
~~~

**This is a complete Java 17 file.** `Pair` appears in the public method signature; `CharMatcher` stays inside the method body; `java.sql.*` belongs to the JDK, while the H2 JDBC driver implementation is discovered at runtime via service provider loading.

The **H2 in-memory** database needs no external DB server, making it ideal for a metadata exercise. The goal is not to provide a production database access pattern or suggest a public database library should force H2 on every consumer; in real projects, driver choice can belong to the application.

### 5.2. `core/CatalogFormatterTest.java`

File **core/src/test/java/com/example/core/CatalogFormatterTest.java**:

~~~java
package com.example.core;

import org.apache.commons.lang3.tuple.Pair;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogFormatterTest {
    @Test
    void normalizesText() {
        assertEquals(Pair.of("normalized", "JAVA"),
                CatalogFormatter.describe("  java  "));
    }

    @Test
    void loadsRuntimeDriver() throws Exception {
        assertTrue(CatalogFormatter.canOpenEmbeddedDb());
    }
}
~~~

Both tests verify the algorithm and confirm the H2 driver is on the **test runtime classpath** via `runtimeOnly`/`runtime` scope. **JUnit is not** a production dependency of the library.

### 5.3. `app/CatalogApplication.java`

File **app/src/main/java/com/example/app/CatalogApplication.java**:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.apache.commons.lang3.tuple.Pair;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner runCatalog() {
        return args -> {
            Pair<String, String> result =
                    CatalogFormatter.describe("  gradle  ");
            System.out.println(result.getLeft() + "=" + result.getRight());
            System.out.println("H2=" +
                    CatalogFormatter.canOpenEmbeddedDb());
        };
    }
}
~~~

`app` intentionally **imports `Pair` directly** to demonstrate that Commons Lang must sit on `core`'s compile API. `app` **does not import Guava or `org.h2.Driver`**, yet both are required when `core` executes.

With a valid graph, the program prints **two deterministic lines from our code**:

~~~text
normalized=GRADLE
H2=true
~~~

Spring Boot/Maven/Gradle logs may also appear; do not treat the snippet above as the entire terminal output.

## 6. Gradle: `java-library` + `maven-publish`

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'publisher'
include 'core', 'app'
~~~

`include` lets Gradle manage subprojects. It **does not automatically publish subprojects**. To upload artifacts, you must configure a publication and target repository.

### 6.2. Complete `core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    api 'org.apache.commons:commons-lang3:3.14.0'
    implementation 'com.google.guava:guava:33.3.1-jre'
    runtimeOnly 'com.h2database:h2:2.3.232'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Catalog Core'
                description = 'Library with explicit API and runtime metadata'
            }
        }
    }
    repositories {
        maven {
            name = 'demo'
            url = rootProject.file('build/repo').toURI()
        }
    }
}
~~~

This is the **complete `core/build.gradle`**, using Groovy DSL. Each key part:

- **java-library** creates the **api, implementation, runtimeOnly** configurations and consumable variants **apiElements/runtimeElements**.
- **maven-publish** creates tasks to generate POM/GMM and publish, without turning `core` into an executable Spring Boot application.
- **from components.java** is the **decisive line**: the publication pulls the **Java component along with dependency metadata**, rather than merely attaching a JAR file.
- **group/version + project name `core`** yield the default coordinates **com.example:core:1.0.0**.
- **api Commons Lang** is exposed on compile API; **implementation Guava** at runtime; **runtimeOnly H2** at runtime; test dependencies are not exposed as runtime libraries.
- **repositories.mavenCentral()** downloads build dependencies. **publishing.repositories** defines where publications are sent. These are two distinct repository configurations.
- The **demo** repository is a **file-backed Maven repository** in **publisher/build/repo**, so the demo requires no tokens or publishing server. Internet/cache access is still needed to fetch libraries.

Do not apply the Spring Boot plugin to `core`; `core` is a plain Java library and must output a plain JAR with classes at standard package paths.

### 6.3. Complete `app/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

`app` uses a project dependency while developing in the same repository. **spring-boot-starter** can omit its version thanks to the Spring Boot plugin paired with the dependency-management plugin; this BOM **does not govern `core`'s dependencies**, because `core` does not apply the Boot plugin.

In `app`, **bootJar** packages the executable Boot JAR. When releasing **core as a library**, we **do not publish `app`'s `bootJar` in place of the `core` JAR**.

### 6.4. Gradle Commands

From the root directory **publisher/** with a valid Gradle 8.5 Wrapper:

~~~bash
./gradlew :core:test :app:bootJar
./gradlew :core:publishMavenJavaPublicationToDemoRepository
~~~

On Windows use **gradlew.bat**. If the repository lacks a wrapper, generate one via an installed Gradle or project scaffolding; `./gradlew` cannot run simply because `build.gradle` exists.

After a successful publish, the local repository is expected to contain:

~~~text
publisher/build/repo/com/example/core/1.0.0/
├── core-1.0.0.jar
├── core-1.0.0.pom
├── core-1.0.0.module
└── checksum artifacts (depends on environment)
~~~

The expected app executable artifact sits at:

~~~text
publisher/app/build/libs/app-1.0.0.jar
~~~

Run:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Business output of the app:

~~~text
normalized=GRADLE
H2=true
~~~

**`app` running properly alone does not prove `core` was published cleanly.** Inspect the metadata and run a consumer **without `project(':core')`** in the next sections.

## 7. What Does Published Gradle Metadata Contain?

### 7.1. `apiElements` and `runtimeElements`

The Gradle Java Library plugin provides **apiElements** for consumer compilation and **runtimeElements** for consumer runtime. With our sample dependencies:

~~~text
apiElements:
  - commons-lang3:3.14.0

runtimeElements:
  - commons-lang3:3.14.0
  - guava:33.3.1-jre
  - h2:2.3.232

not exposed as consumer dependencies:
  - junit-jupiter:5.11.3
  - junit-platform-launcher:1.11.3
~~~

This diagram is a **logical representation**. In real JSON, attributes, variant metadata, checksums, and version declarations have their own structure. Transitive dependencies of Guava or H2 are also resolved via their own metadata.

### 7.2. Maven POM Generated from the Java Component

When using **from components.java** on `java-library`, Gradle generates a POM with matching scopes. The dependencies section looks roughly like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
        <version>33.3.1-jre</version>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <version>2.3.232</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This is an **expected fragment**, not the full POM verbatim. Gradle may include other valid XML elements and a marker comment indicating that a corresponding `.module` file exists.

Key mappings:

| Gradle `java-library` Declaration | Maven POM Generated from Java Component |
| --- | --- |
| **api** | **compile** |
| **implementation** | **runtime** |
| **runtimeOnly** | **runtime** |
| **testImplementation / testRuntimeOnly** | Not exposed as consumer compile/runtime dependencies |
| **compileOnly** | Not treated as a published runtime dependency; Maven POM cannot fully represent compile-only semantics |

**Key takeaway:** Guava is not placed on the consumer `compileClasspath` as an exported API by `core`, yet still appears on the consumer `runtimeClasspath`. That is the right behavior.

### 7.3. GMM Is Richer Than a POM

Gradle Module Metadata has **variants and attributes** selected by usage such as `java-api`/`java-runtime`. It can also express **rich version constraints, dependency constraints, capabilities, and feature variants**. Maven POMs lack equivalent constructs for every feature, so mapping can lose fidelity.

Gradle typically publishes **both POM and `.module`**, along with a marker comment in the POM telling Gradle that richer module metadata exists. Maven clients continue reading the POM; Gradle consumers can prefer `.module`. If a proxy/repository strips `.module` or only serves `metadataSources.mavenPom()`, Gradle may fall back to the POM and variant selection can become less precise.

### 7.4. Inspect Generated Files Before Publishing

~~~bash
./gradlew :core:generatePomFileForMavenJavaPublication
./gradlew :core:generateMetadataFileForMavenJavaPublication
~~~

Typical build-local files:

~~~text
core/build/publications/mavenJava/pom-default.xml
core/build/publications/mavenJava/module.json
~~~

After publishing, they are named per Maven layout as **core-1.0.0.pom** and **core-1.0.0.module**. Verify the **exact dependencies/variants/scopes**, not just that the files exist.

If build tooling adds plugins modifying the publication, contents may differ. For CI verification, parse the XML/JSON and compare dependencies by **group/name/version/scope/variant** rather than comparing line order.

## 8. Inspecting Classpaths and Outgoing Variants Inside the Workspace

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :core:dependencies --configuration runtimeClasspath
./gradlew :core:outgoingVariants
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

**Expected:**

- **core compileClasspath:** Commons Lang + Guava; H2 not required.
- **core runtimeClasspath:** Commons Lang + Guava + H2.
- **core outgoingVariants:** `apiElements` and `runtimeElements` with attributes/artifacts.
- **app compileClasspath:** has Commons Lang via `core`'s API; `core` does not expose Guava/H2 on the compile API.
- **app runtimeClasspath:** has Commons Lang + Guava + H2 for running the library.

**Important:** `core`'s `compileClasspath` (for the **declaring module**) and `app`'s `compileClasspath` (for the **consumer**) are not the same thing. Guava must be present for `core`'s compiler because `core` code imports `CharMatcher`, yet the consumer does not need to see Guava when calling only the public API using `Pair`.

These commands help explain the internal build, yet **do not replace post-publish consumption testing**.

## 9. Independent Gradle Consumer: Testing Real Metadata Without a Project Dependency

Create a **second project** alongside `publisher`:

~~~text
workspace/
├── publisher/
│   └── build/repo/com/example/core/1.0.0/...
└── consumer/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/com/example/consumer/ConsumerMain.java
~~~

File **consumer/settings.gradle**:

~~~groovy
rootProject.name = 'consumer'
~~~

File **consumer/build.gradle**:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example.consumer'
version = '1.0.0'

repositories {
    maven {
        url = uri('../publisher/build/repo')
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example:core:1.0.0'
}

application {
    mainClass = 'com.example.consumer.ConsumerMain'
}
~~~

This is a **complete `build.gradle` file**. It uses the published artifact's coordinates and **knows nothing about `project(':core')`**, forcing Gradle to read repository metadata. The `application` plugin creates the **run** task and includes Java plugin capabilities.

File **consumer/src/main/java/com/example/consumer/ConsumerMain.java**:

~~~java
package com.example.consumer;

import com.example.core.CatalogFormatter;
import org.apache.commons.lang3.tuple.Pair;

public class ConsumerMain {
    public static void main(String[] args) throws Exception {
        Pair<String, String> result =
                CatalogFormatter.describe("  gradle  ");
        System.out.println(result.getLeft() + "=" + result.getRight());
        System.out.println("H2=" +
                CatalogFormatter.canOpenEmbeddedDb());
    }
}
~~~

This is a complete Java 17 class. Do **not** declare Commons Lang, Guava, or H2 directly in `consumer/build.gradle`. They must arrive from `core`'s metadata.

From **workspace/consumer**, with a compatible Gradle installed:

~~~bash
gradle run
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
~~~

If the consumer has a wrapper, use **./gradlew** instead of **gradle**. To run, JDK 17 must be present and dependencies must be fetched from Maven Central/cache.

**The two lines the application prints when metadata is accurate:**

~~~text
normalized=GRADLE
H2=true
~~~

In the graph, **compileClasspath** should contain `core` + Commons Lang; **runtimeClasspath** should additionally include Guava/H2. `core`'s JUnit must not enter the consumer's runtime graph. If runtime JDBC fails, inspect the H2 dependency in the runtime variant/POM, repositories, and exception messages.

**An independent consumer is a stronger test than the reactor:** it forces the tool to read published identity/metadata instead of reading the project graph from the source workspace.

## 10. Maven: Aggregator, Parent, and Dependency Relationships

In Maven multi-module builds, distinguish:

- **Aggregation**: root POM declares **modules**, letting Maven Reactor build multiple modules per the dependency graph.
- **Inheritance**: child POM declares **parent**, inheriting configuration, group/version, `dependencyManagement`, `pluginManagement`, and properties.
- **Dependency**: app POM declares `core` by Maven coordinates; Maven resolves it from the reactor or a repository.
- **Publication**: install/deploy **artifact + POM** of each module; the parent POM may also need to be published separately.

**Aggregation does not imply inheritance**. A child listed in `<modules>` does not inherit parent config unless it declares `<parent>`. Conversely, if a **published `core` POM references an internal parent**, external consumers outside the reactor must be able to resolve that parent POM.

### 10.1. Complete Root `pom.xml`

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
    <artifactId>publisher-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

The root is both **aggregator** and **parent** of `core`/`app`. It packages no JAR because of **packaging pom**. The Spring Boot parent provides dependency management for app starters without turning `core` into a Boot application.

### 10.2. Complete `core/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>publisher-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>com.google.guava</groupId>
            <artifactId>guava</artifactId>
            <version>33.3.1-jre</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

This is an independent `core` POM in the Maven Reactor. The parent provides group/version and `dependencyManagement` so `starter-test` omits an explicit version.

**Difference from Gradle Java Library:** Maven's default `compile` scope applies to both **Commons Lang** and **Guava**, because `core` code needs both at compile time. Maven **has no `implementation` configuration separate from the public API**. Do not change Guava to `runtime` scope in the `core` POM just to "hide" it from consumer compile classpaths, because `core`'s own compiler imports Guava `CharMatcher`.

With the hand-authored Maven POM here:

~~~text
Commons Lang : Maven compile
Guava        : Maven compile
H2           : Maven runtime
Starter Test : Maven test
~~~

With the POM **generated by Gradle `java-library`**:

~~~text
Commons Lang : Maven compile
Guava        : Maven runtime
H2           : Maven runtime
JUnit        : not a consumer runtime/compile dependency
~~~

Both approaches build a working `core`, yet Gradle expresses **public API vs implementation more cleanly**. This is a Maven dependency model limitation to understand when comparing published POMs.

### 10.3. Complete `app/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>publisher-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**App** depends on `core` via GAV **com.example:core:1.0.0**. In the same reactor, Maven builds `core` before `app`. The Boot Maven Plugin appears only in `app` and executes **repackage** to create the executable artifact; **core remains an ordinary library JAR**.

To package the app with Maven:

~~~bash
./mvnw clean verify
java -jar app/target/app-1.0.0.jar
~~~

Or use **mvn clean verify** when there is no wrapper yet a compatible Maven is installed. On Windows use **mvnw.cmd**. With the main class in section 5 and proper dependencies, the application's two output lines remain **normalized=GRADLE** and **H2=true**.

## 11. Maven: Install/Deploy the POM Along with the Parent

A dangerous publishing mistake is **uploading only `core-1.0.0.jar` without its POM**, or publishing a `core` POM whose **parent cannot be resolved**.

From the `publisher` root:

~~~bash
./mvnw -pl core -am clean install
~~~

This selects module **core** and required reactor projects, then installs the JAR/POM into the local Maven repository. For complex project setups, confirm the root parent is installed as well; you can run **mvn install** at root to install the entire reactor.

In the local Maven repository, you should expect:

~~~text
~/.m2/repository/com/example/publisher-parent/1.0.0/publisher-parent-1.0.0.pom
~/.m2/repository/com/example/core/1.0.0/core-1.0.0.pom
~/.m2/repository/com/example/core/1.0.0/core-1.0.0.jar
~~~

When deploying to an organization's remote repository, the parent **publisher-parent:1.0.0** must also be present; the Spring Boot parent is a public artifact resolvable from standard repositories. If the `core` POM points to another **internal BOM/parent**, that metadata must also be published with appropriate access permissions.

**Distinguish `package`, `install`, and `deploy`:**

- **package**: builds artifacts inside **target/**.
- **install**: installs artifacts/POMs into the **local Maven repository**.
- **deploy**: uploads artifacts/POMs to a configured **remote Maven repository** (with proper credentials/permissions).

Running **mvn package** alone will not make `core` visible to consumers on other machines. Having only the `core` JAR in a repo without its POM also breaks transitive dependency propagation.

### 11.1. Inspecting Effective POM and Dependency Tree

~~~bash
./mvnw -pl core help:effective-pom
./mvnw -pl app dependency:tree
~~~

**effective-pom** applies the parent and `dependencyManagement` to show the model Maven builds with. **dependency:tree** explains how `core`, Commons Lang, Guava, and H2 reach `app` transitively.

**However, the effective POM does not replace reading the published POM.** The published `core` POM still keeps its `<parent>` tag, so consumers must be able to resolve that parent. Test with a separate consumer **outside the reactor**, declaring only `core`'s GAV and the target repository.

### 11.2. A Dependency in a Maven Consumer

A Maven consumer can declare:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

This is a **fragment inside `<dependencies>` of a consumer `pom.xml`**, not a standalone runnable POM. The consumer reads the installed/deployed `core` POM and its parent. If the parent/BOM/version is missing, Maven fails before resolving the right dependency graph.

## 12. BOM, Constraints, and Version Policies When Publishing

### 12.1. A BOM Is Version Management, Not an Automatic Runtime Library

In Maven, a BOM is imported inside **dependencyManagement**, for example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is a **configuration snippet** for another POM; do not insert it into the exercise's root POM since the root already uses the Spring Boot parent. A BOM manages versions of declared dependencies and **does not put every dependency listed in the BOM onto the classpath**.

In Gradle, you can use a native **platform** for dependency constraints:

~~~groovy
dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    api 'org.springframework.boot:spring-core'
}
~~~

This is an **illustrative snippet for a `java-library` intending to export BOM constraints into its public API**, not something to add to the demo `core`. Gradle GMM represents platforms/constraints more richly than a POM; if publishing to Maven consumers, check generated `dependencyManagement`/versions and consumer resolution.

### 12.2. Declared Versions vs Resolved Versions

Gradle's Maven Publish Plugin can publish **declared versions** from dependency declarations. However, dependency locking, conflict resolution, rich constraints, or dynamic selectors can cause the **resolved version** actually tested to differ from the declared text.

Gradle supports **versionMapping**. For example, replacing `core`'s publication block with:

~~~groovy
mavenJava(MavenPublication) {
    from components.java

    versionMapping {
        usage('java-api') {
            fromResolutionOf('runtimeClasspath')
        }
        usage('java-runtime') {
            fromResolutionResult()
        }
    }
}
~~~

This is a **replacement fragment**, not a complete `build.gradle`. It maps versions from resolution results, aligning the published POM closer to what was built and tested. Do not assume `versionMapping` handles every rich constraint or forces every consumer onto identical versions: consumers still apply their own dependency resolution rules.

In the demo `core`, all three main dependencies declare fixed versions, so POM versions are easy to verify without `versionMapping`.

### 12.3. Never Publish Unresolvable Versionless Dependencies

A versionless dependency in a published POM is **valid only** when a parent, `dependencyManagement`, or standard mechanism actually supplies the version and is accessible to consumers. Never strip versions to tidy up a POM while forgetting the parent/BOM.

Similarly, Gradle module metadata with constraints that cannot resolve to valid versions will fail consumers. Always inspect the **published metadata**, rather than inferring solely from source configuration.

## 13. Boot Executable Artifacts Differ from Java Component Publications

The Spring Boot Gradle Plugin documents publishing **bootJar** via a `MavenPublication` attaching the artifact directly. Illustrative fragment:

~~~groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
~~~

To use this fragment, the `app` module must apply **maven-publish** and configure a publishing repository. However, **`artifact tasks.named('bootJar')` only specifies the file to upload**; it **does not automatically generate full Java library dependency metadata** the way **from components.java** does.

Do not mix a Boot executable JAR into a Java component publication and expect consumers to compile against it like an ordinary library: **BOOT-INF/classes** is not the classpath root of a library JAR. If an organization must publish both a plain JAR and an executable app, design separate publications/classifiers/coordinates to avoid overwriting artifacts and clearly guide consumers on which to use.

**Practical rule:** `core` is released as a **Java library + POM/GMM**; `app` is released as an **executable Boot JAR/container image**. This keeps dependency contracts clear in multi-module Spring Boot projects.

## 14. When Maven and Gradle Interpret Metadata Differently

### 14.1. Expressiveness Differences

GMM expresses variants, capabilities, and rich versions, whereas a Maven POM primarily expresses scopes, `optional`, exclusions, and `dependencyManagement`. Features such as **feature variants**, **compileOnlyApi**, or capability conflict rules may **not map completely** to a POM.

When Gradle publishes a component with features that cannot be fully expressed in a POM, Gradle emits warnings. Never blindly use **suppressPomMetadataWarningsFor** just to silence the warning: suppressing it does not fix the contract for Maven consumers. Verify compatibility or provide an alternative artifact/publication if needed.

### 14.2. POM Present, `.module` Missing

Maven consumers still read the POM. Gradle can infer variants from POM scopes, yet loses Gradle-native fidelity. If a repository/proxy strips `.module` or only exposes `metadataSources.mavenPom()`, Gradle consumers may resolve differently than when reading GMM.

### 14.3. `.module` Present, POM Missing

Maven consumers do not understand GMM as a POM substitute. If Maven support is required, you must publish a valid POM alongside the artifact. Configuring **maven-publish** from the Java component handles this.

### 14.4. Inconsistent Metadata Caching

If the same GAV **com.example:core:1.0.0** is overwritten repeatedly, one consumer may retain an older cached POM/JAR while another fetches newer module metadata. Releases should be **immutable**: bump the version whenever the dependency graph or bytes change, and publish JAR/POM/`.module`/checksums atomically. Never fix broken metadata by overwriting an already released version.

## 15. CI: Verifying Publications via Consumer Contracts

### 15.1. Gradle Workflow

A pipeline validating the library can run:

~~~bash
./gradlew clean :core:test :app:bootJar
./gradlew :core:generatePomFileForMavenJavaPublication
./gradlew :core:generateMetadataFileForMavenJavaPublication
./gradlew :core:publishMavenJavaPublicationToDemoRepository
~~~

Then verify:

1. The repository contains **core-1.0.0.jar, core-1.0.0.pom, core-1.0.0.module**.
2. The POM lists **Commons Lang as `compile`**, **Guava/H2 as `runtime`**, and does not publish JUnit under compile/runtime.
3. The GMM lists **Commons Lang in API and runtime**, **Guava/H2 in runtime**, and no JUnit in consumer-facing variants.
4. Group/artifact/version match, with no disallowed dynamic versions.
5. An independent consumer compiles and runs, printing **normalized=GRADLE** and **H2=true**.
6. The app Boot JAR also runs cleanly and is **not mistakenly picked as the core artifact**.

**Automation tip:** parse the POM with an XML parser and `.module` with a JSON parser, comparing dependencies by group/name/version/scope/variant. Avoid full-text line-by-line diffs, as Gradle versions may add attributes or reorder entries.

### 15.2. Maven Workflow

~~~bash
./mvnw clean verify
./mvnw -pl core -am install
./mvnw -pl core help:effective-pom
./mvnw -pl app dependency:tree
~~~

Then inspect the parent/core POMs actually installed in the local Maven repository and run a consumer outside the reactor. If deploying to a remote server, verify the **parent POM, internal BOMs, and access permissions**, not only the core JAR.

### 15.3. Diagnosing Errors from the Consumer Side

| Symptom | Check First |
| --- | --- |
| Compile fails missing `Pair` | Is Commons Lang in the API variant / POM `compile` scope? |
| Runtime `NoClassDefFoundError` for Guava | Is Guava in `runtimeElements` / POM `runtime` scope? |
| Runtime reports `No suitable driver` for `jdbc:h2` | Is H2 in the runtime graph? |
| JUnit appears in production runtime | Were test scopes/configurations published wrongly? |
| Non-resolvable parent POM | Were internal parent/BOM published and accessible by consumer repositories/permissions? |
| Gradle and Maven pick different dependencies | Compare `.module` vs POM, versions, constraints, `metadataSources` |
| App Boot JAR fails to work as a library | Was `bootJar` mistakenly published as a plain Java component? |

## 16. Common Errors and Remedies

**1. Publishing only the JAR without POM or GMM.** Consumers cannot discover transitive dependencies. Use **maven-publish `from components.java`** for Gradle libraries or full Maven install/deploy of both JAR and POM.

**2. Using Gradle `java` plugin while declaring `api`.** **`api`** belongs to `java-library`. Switch public-API library modules to **`java-library`**.

**3. Placing Commons Lang in `implementation` even though the public API uses `Pair`.** Consumers need `Pair` at compile time. Move Commons Lang to **`api`** or redesign the public API not to expose that type.

**4. Placing Guava in `api` even though it is internal-only.** Does not crash immediately, yet leaks implementation details. Use **`implementation`**.

**5. Removing Guava from runtime to hide implementation.** `CharMatcher` is still invoked at runtime. `core`'s implementation dependencies **must exist** on consumer runtime.

**6. Placing H2 in `testImplementation` while production features use the H2 JDBC URL.** Tests pass yet the app lacks the driver. Use `runtimeOnly` if the library genuinely commits to providing that runtime driver.

**7. Publishing JUnit as a runtime dependency.** Consumers receive unnecessary test tooling. Keep JUnit in `testImplementation` or Maven `test` scope.

**8. Uploading an artifact file directly in Gradle without `components.java`.** The file uploads, yet dependency metadata is missing. For libraries, use **from components.java**.

**9. Using a Boot executable JAR as a library.** Classes live under `BOOT-INF/classes`, unsuitable for standard consumer compilation. Publish a plain JAR from `core`.

**10. Assuming Gradle `build.success` equals `publish.success`.** Internal builds use project dependencies and differ from external consumers. Publish and test with an independent consumer.

**11. Maven `core` POM references an undeployed private parent.** Consumers cannot construct the effective model. Publish the parent POM and internal BOMs, or design a self-contained POM.

**12. Switching Maven Guava from `compile` to `runtime` to mimic Gradle `implementation`.** Maven `core` needs Guava at compile time; `runtime` scope breaks `core` compilation. Understand Maven scope limits instead of misconfiguring.

**13. Running only Maven `package`.** `package` does not install/deploy artifacts to consumer repositories. Use `install`/`deploy` per workflow.

**14. Checking only Gradle `.module` when Maven consumers exist.** Maven reads the POM. QA the POM and test a Maven consumer.

**15. Checking only the POM when Gradle consumers exist.** Gradle may prefer GMM with different variants. QA both.

**16. Suppressing POM metadata warnings without reading them.** Silencing warnings does not convert rich constraints/capabilities into POM equivalents. Evaluate consumer compatibility.

**17. Missing versions in published POM.** Check BOM/parent/`dependencyManagement` and `versionMapping`. Never publish versionless dependencies without a resolution source.

**18. Confusing publish repositories with resolution repositories.** **`repositories`** downloads build dependencies; **`publishing.repositories`** specifies where artifacts are written. Configure both properly.

**19. Publication `artifactId` differs from consumer coordinates.** Check **`groupId`/`artifactId`/`version`** in the generated POM and repository URI. Do not guess from project or directory names.

**20. Overwriting the same release GAV with different content.** Caching causes consumers to see inconsistent metadata. Keep release versions immutable; never mutate an already published release.

**21. Confusing Maven parent with aggregator.** Listing `<modules>` does not make child POMs inherit configuration. Children must declare `<parent>` to use inheritance.

**22. Testing consumers only via `project(':core')`.** That does not test publication. Create a separate consumer project using **com.example:core:1.0.0**.

**23. Assuming a BOM automatically pulls in all libraries.** A BOM manages versions/constraints only; dependencies must still be declared in the right configurations.

**24. Testing only API compilation and forgetting runtime.** Consumers can compile cleanly and still crash on `CharMatcher` or the JDBC driver at runtime. Runtime smoke tests are mandatory.

## 17. Checklist for Publishing a Library for Other Teams

- [ ] Separate **library `core`** from **Spring Boot `app`**.
- [ ] Gradle library module uses **`java-library` + `maven-publish`**.
- [ ] Gradle publication uses **from components.java**.
- [ ] API dependencies exposing public types are declared **`api`**.
- [ ] Implementation dependencies needed at runtime appear in `runtimeElements`/POM `runtime`.
- [ ] Runtime-only providers/drivers appear in consumer runtime.
- [ ] JUnit and test support are never published as product dependencies.
- [ ] Maven POM has accurate scopes and published, resolvable parent/BOMs.
- [ ] Generated POM has accurate `groupId`/`artifactId`/`version` and dependency versions.
- [ ] Gradle `.module` has accurate `apiElements`/`runtimeElements` and attributes.
- [ ] Checksums/release identity are preserved without overwriting release artifacts.
- [ ] Both Maven and Gradle consumers are tested independently if both ecosystems are supported.
- [ ] App executable JAR is never accidentally published as a library.
- [ ] CI catches publish errors, parses metadata, and runs consumer smoke tests.
- [ ] Whenever versions/BOMs/constraints change, re-verify the contract.

## 18. Official Documentation

- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot — Publishing with the Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/publishing.html)
- [Spring Boot — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Conclusion:** In multi-module Spring Boot projects, a successful build **does not prove published metadata is accurate**. Publish a plain JAR for the library alongside **Maven POM and Gradle Module Metadata**, map **api/implementation/runtimeOnly** accurately, keep test dependencies out of production, handle parent/BOM/versions cleanly, and verify with an **independent consumer**. Spring Boot executable JARs belong to application deployment and never substitute for publishing a Java library.