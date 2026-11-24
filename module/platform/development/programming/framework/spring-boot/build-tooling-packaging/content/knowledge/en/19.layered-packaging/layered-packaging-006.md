# Controlling Layer Order and Internal Library Placement in Spring Boot

## 1. Objectives and Expected Outcomes

When packaging a Spring Boot application into an executable JAR, dependencies are bundled into the archive so the app runs standalone. If a container image is built by copying the **entire JAR**, even a minor change in application code can cause the layer holding the JAR to change. **Layered archives** solve the problem of organizing contents into layers with different rates of change, giving image-building tools a better chance to reuse cache.

In multi-module projects, the hard question is not merely “enable layers”, but:

- Is the internal `core` library consumed as a **Maven reactor module**, a **Gradle project dependency**, or via **published GAV coordinates**?
- When the `core` library changes, which part of the image do you want invalidated?
- How should company libraries in **release**, **SNAPSHOT**, and same-repository module forms be distinguished?
- Which **matchers** claim the right library into the desired layer, and which **layerOrder** fits your caching goals?
- How do you verify `BOOT-INF/layers.idx` of the **final JAR**, rather than just trusting XML/Groovy config?
- How do you build an image from layers and run the application after extraction?

This lesson belongs to the **Layered Packaging** section of Spring Boot Build Tooling Packaging. We will use the same Java 17 application in both Maven and Gradle, featuring an internal `core` library module and an executable `app` module. Once built, learners can inspect the exact **layer order and placement of `core-1.0.0.jar`**, run a Java verifier, and build a Docker image via `jarmode=tools`.

**Illustrated versions:** Java 17, Spring Boot 3.3.5, Maven 3.9.x, or Gradle 8.5. These versions are chosen for practice and do not represent the latest releases. Spring Boot 3.3 configuration is used consistently with the `jarmode=tools` command; older versions may use `layertools` and different commands.

## 2. What Is a Layer, and What Is It Not?

An executable Spring Boot JAR holds both the application and dependencies in one archive. Example:

~~~text
app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/LayeredApplication.class
    ├── lib/
    │   ├── core-1.0.0.jar
    │   ├── spring-boot-3.3.5.jar
    │   └── ...
    └── layers.idx
~~~

The **BOOT-INF/layers.idx** file is metadata indicating which archive paths belong to which layer. An illustrative snippet (not the complete real contents):

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/spring-boot-3.3.5.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/"
- "internal-modules":
  - "BOOT-INF/lib/core-1.0.0.jar"
- "application":
  - "BOOT-INF/classes/"
~~~

Here **internal-modules** is a custom layer defined for this lesson; Spring Boot does not generate this name by default.

Three locations must be distinguished:

1. **Physical location in the JAR:** the `core` library still resides at `BOOT-INF/lib/core-1.0.0.jar` (inside the executable JAR). Changing its layer does not turn it into `BOOT-INF/internal-modules/core.jar`.
2. **Layer assignment in `layers.idx`:** `core-1.0.0.jar` belongs to `internal-modules`, `application`, or another layer per the rules.
3. **Directory after extraction with jarmode tools:** the tool creates directory groups per layer for Dockerfile COPYs. Spring Boot 3.3 has an extraction layout geared toward fast startup and can generate a thin launcher JAR alongside libraries at optimized paths; do not assume relative paths after extraction match `BOOT-INF/lib` prior to extraction.

**A layer in this lesson is not a Java JPMS layer, a Spring service/controller/repository architectural layer, or bean loading order.** Layer order serves **packaging and cache efficiency**; it does not alter dependency resolution, classpath precedence, transaction ordering, or application lifecycle.

### 2.1. Does Layering Change Runtime Behavior?

With valid configuration, the executable Boot JAR still runs via:

~~~bash
java -jar app-1.0.0.jar
~~~

The Boot loader still finds application classes and runtime dependencies according to the archive layout. Adding or modifying **`layers.idx`** is not a way to fix a `ClassNotFoundException` caused by a mispackaged library. Verify separately: **(1) `core` is present on the runtime classpath and (2) `core` is assigned to the right layer**.

### 2.2. Why Does Docker Caching Benefit?

Suppose an image has six COPY instructions, ordered from least volatile to most volatile:

~~~text
Layer 1: dependencies
Layer 2: spring-boot-loader
Layer 3: internal-releases
Layer 4: snapshot-dependencies
Layer 5: internal-modules
Layer 6: application
~~~

If only an application class changes, earlier COPY steps for dependency libraries have a chance for cache hits. If `core` changes, layers preceding `internal-modules` can retain cache. This is the primary advantage of layered builds.

**Layering does not shrink the total dependency byte size.** An image with more layers also has overhead. Whether it is beneficial must be measured by image layers, cache hit rates, rebuild/pull speeds, and actual change patterns.

## 3. Four Default Layers and Default Order in Spring Boot 3.3

When building a layered executable JAR with Spring Boot Maven/Gradle Plugin 3.3, the default configuration splits as follows:

| Default layer | Typical target | Reason for separation |
| --- | --- | --- |
| `dependencies` | Release dependencies without SNAPSHOT in their version | Typically change infrequently |
| `spring-boot-loader` | Spring Boot loader classes | Change when upgrading loader/plugin |
| `snapshot-dependencies` | External dependencies with SNAPSHOT in their version | Change more frequently |
| `application` | Application classes/resources and local module/project dependencies | Change with the build's own source code |

**Default layer order** documented by Spring Boot 3.3:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

This order puts less volatile parts **first** and more volatile parts **later** to assist caching. It is the default policy; not every application is required to keep it unchanged.

### 3.1. Local Maven Module and Gradle Project Dependency

The statement “internal libraries belong to the `application` layer by default” carries an important condition:

- **Maven:** Spring Boot detects **module dependencies belonging to the current reactor/build**. A library resolved solely from `~/.m2/repository` outside the current reactor may be treated as an ordinary dependency.
- **Gradle:** Spring Boot detects **project dependencies** like `implementation project(':core')`. Replacing that with repository coordinates `implementation 'com.example:core:1.0.0'` stops it from being treated automatically as a project dependency.

This is the difference between **organizational origin** (“written in-house by our company”) and **how the resolver represents the module** (“part of the current build vs. fetched from a repository”). You cannot guess the layer from a `com.example` prefix without checking the matchers and how the build resolves the dependency.

### 3.2. SNAPSHOT Dependencies Can Belong to Multiple Groups

Consider three libraries:

~~~text
com.example:core:1.0.0                   # local module/project in current build
com.example:company-utils:2.0.0          # published
com.example:company-utils:2.1.0-SNAPSHOT # published yet mutable
~~~

Under default layers, local `core` normally goes to `application`; released `company-utils` goes to `dependencies`; SNAPSHOT `company-utils` goes to `snapshot-dependencies`. Grouping internal libraries separately requires custom rules.

A local `core` module with version **1.0.0-SNAPSHOT** will be affected by matcher order: if you want it in a dedicated local layer, the local matcher must **claim it before** the SNAPSHOT matcher.

## 4. Designing Six Layers for a Multi-Module Project

This lesson defines two extra layers:

- **internal-modules:** `core` and libraries built from modules/projects in the current build.
- **internal-releases:** published company dependencies under group `com.example` not claimed by an earlier matcher.

Desired outcome:

| Library or entry | Dependency type | Desired layer |
| --- | --- | --- |
| Commons Lang release | External release | `dependencies` |
| Spring Boot loader | Loader classes | `spring-boot-loader` |
| `com.example:company-utils:2.0.0` | Published internal release | `internal-releases` |
| `com.example:company-utils:2.1.0-SNAPSHOT` | Published SNAPSHOT | `snapshot-dependencies` |
| `com.example:core:1.0.0` | Maven reactor module / Gradle project | `internal-modules` |
| `LayeredApplication.class` and resources | App code | `application` |

**Membership decision order (matcher order):**

~~~text
1. Is local Maven module / Gradle project?  -> internal-modules
2. Has a SNAPSHOT version?                  -> snapshot-dependencies
3. Group matches com.example?              -> internal-releases
4. Everything else                         -> dependencies
~~~

**Layer output order (layerOrder):**

~~~text
dependencies
spring-boot-loader
internal-releases
snapshot-dependencies
internal-modules
application
~~~

These two orders **are not the same and must be controlled independently**. Matcher order is evaluated **top to bottom**; each entry claimed by an earlier rule is unavailable to later rules. `layerOrder` determines the order layers are written/extracted, serving the order of COPY steps in the Dockerfile.

### 4.1. What If You Swap SNAPSHOT and Internal Group Priority?

Suppose there is a dependency `com.example:company-utils:2.1.0-SNAPSHOT`: it matches both **`*:*:*SNAPSHOT`** and **`com.example:*`**. Under the design above, it lands in **snapshot-dependencies** because the SNAPSHOT matcher precedes the group matcher.

If you want all published company libraries—including SNAPSHOTs—in `internal-releases`, rename the layer to `internal-published` for accuracy, place the group matcher before SNAPSHOT, and accept that this layer will change more often. No single order fits every team; express your policy explicitly and write tests for it.

### 4.2. The Catch-All Must Be Last

An `into` or `intoLayer` block **without a matcher** claims every entry not claimed by prior rules. Putting a catch-all at the top of the dependencies list leaves later rules with nothing to claim.

Incorrect goal:

~~~groovy
dependencies {
    intoLayer('dependencies')
    intoLayer('internal-modules') {
        includeProjectDependencies()
    }
}
~~~

This is an **erroneous fragment**, not a complete Gradle file. The right way is putting `internal-modules` first and the `dependencies` catch-all last.

## 5. Shared Java 17 Code for Both Maven and Gradle

Let's create two modules: a small library and a Spring Boot application depending on that library.

### 5.1. Project Structure

~~~text
layered-demo/
├── pom.xml                       # root if using Maven
├── settings.gradle               # root if using Gradle
├── core/
│   ├── pom.xml                   # Maven core
│   ├── build.gradle              # Gradle core
│   └── src/main/java/com/example/core/SkuFormatter.java
└── app/
    ├── pom.xml                   # Maven app
    ├── build.gradle              # Gradle app
    ├── src/layers.xml            # Maven custom layering
    └── src/main/java/com/example/app/LayeredApplication.java
~~~

**Choose Maven or Gradle** when practicing; the two sets of build files are alternatives. All Java source below works with both.

### 5.2. Core Library Module

File `core/src/main/java/com/example/core/SkuFormatter.java`:

~~~java
package com.example.core;

import java.util.Locale;

public final class SkuFormatter {

    private SkuFormatter() {
    }

    public static String normalize(String input) {
        return "SKU-" + input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

This is a **complete Java 17 file**. `String.strip()` has existed since Java 11; `Locale.ROOT` ensures consistent upper-casing across machines. Given input `" 42 "`, the method returns **SKU-42**.

We **do not apply the Spring Boot Plugin to `core`**. `core` needs to build a library JAR with `com/example/core/SkuFormatter.class` directly under the standard package path. If `core` were repackaged as a Boot executable archive (with classes under `BOOT-INF/classes`), it would no longer work as a regular dependency library.

### 5.3. App Application Module

File `app/src/main/java/com/example/app/LayeredApplication.java`:

~~~java
package com.example.app;

import com.example.core.SkuFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayeredApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayeredApplication.class, args);
    }

    @Bean
    CommandLineRunner proof() {
        return args -> System.out.println(
                "LAYERING_OK:" + SkuFormatter.normalize(" 42 "));
    }
}
~~~

This is also a **complete Java 17 file**. The application uses basic `spring-boot-starter`, needing no HTTP server or database. When running the proper executable JAR, it prints the exact line defined by the source:

~~~text
LAYERING_OK:SKU-42
~~~

Spring Boot may also print a banner and logs. The snippet above is not the entire terminal output.

## 6. Maven: Multi-Module Root POM

Create `layered-demo/pom.xml`:

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
    <artifactId>layered-demo</artifactId>
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

The root POM acts as both an **aggregator** via `modules` and a **parent** so child POMs inherit group/version. It produces no executable JAR because `packaging=pom`.

### 6.1. Complete core/pom.xml

File `layered-demo/core/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>layered-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>
</project>
~~~

`core` builds a plain library JAR with coordinates `com.example:core:1.0.0`. It **does not** apply `spring-boot-maven-plugin`. This module is recognized as a local module when present in the **active reactor**.

### 6.2. Complete app/pom.xml

File `layered-demo/app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>layered-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

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
                <configuration>
                    <layers>
                        <enabled>true</enabled>
                        <configuration>${project.basedir}/src/layers.xml</configuration>
                    </layers>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Key points:**

- Spring Boot Maven Plugin is declared **only in `app`** to run the `repackage` goal.
- When using `spring-boot-starter-parent`, the `repackage` execution is already managed in inherited config; do not declare a duplicate execution.
- `layers.enabled=true` retains layer metadata in the executable JAR.
- `layers.configuration` points to the actual XML file at `app/src/layers.xml`, read by the plugin at build time.
- The `core` dependency must exist in the runtime graph; removing the dependency to push `core` out of some layer will break the application.
- The Boot JAR artifact defaults to `app-1.0.0.jar` under `app/target/`.

### 6.3. Complete and Clearly Ordered app/src/layers.xml

Create `layered-demo/app/src/layers.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
                            https://www.springframework.org/schema/boot/layers/layers-3.3.xsd">

    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application" />
    </application>

    <dependencies>
        <into layer="internal-modules">
            <includeModuleDependencies />
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="internal-releases">
            <include>com.example:*</include>
        </into>
        <into layer="dependencies" />
    </dependencies>

    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>internal-releases</layer>
        <layer>snapshot-dependencies</layer>
        <layer>internal-modules</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

**This is a complete `layers.xml` file**, using the Spring Boot 3.3 schema and custom layer order. Breakdown:

- `application`: the `org/springframework/boot/loader/**` matcher claims loader classes; the following catch-all claims remaining app classes/resources.
- `dependencies` first: `includeModuleDependencies` claims **module dependencies belonging to the current Maven build** into **internal-modules**.
- `dependencies` second: `*:*:*SNAPSHOT` claims remaining external snapshots.
- `dependencies` third: `com.example:*` claims published dependencies under the internal group not claimed by the prior two rules.
- `dependencies` last: catches everything remaining into **dependencies**.
- `layerOrder` lists all six layers. **Do not confuse** that order with the `into` order above.

In an example containing only `core` and the Spring Boot starter, there may **not yet be any libraries in `internal-releases` or `snapshot-dependencies`**; that is not an error. The rules exist to handle future additions if the project adds matching dependencies.

### 6.4. Maven Build from Reactor Root

From `layered-demo/`, run:

~~~bash
mvn -pl app -am clean package
~~~

If the repository has a Maven Wrapper:

~~~bash
./mvnw -pl app -am clean package
~~~

`-pl app` selects the module to build, and `-am` builds reactor modules that `app` depends on, including `core`. **Having `core` inside the current reactor** is what allows `includeModuleDependencies` to recognize it as a local module. Running `app` standalone after `core` was only installed into the local Maven repository can change matcher results.

After a successful build:

~~~text
app/target/app-1.0.0.jar
~~~

Run the application:

~~~bash
java -jar app/target/app-1.0.0.jar
~~~

Stdout line printed by the app:

~~~text
LAYERING_OK:SKU-42
~~~

If running Maven via `mvn`, a compatible Maven installation must be present. On Windows, use `mvnw.cmd` instead of `./mvnw` when using a wrapper. A wrapper does not appear automatically simply from creating a POM.

## 7. Gradle Multi-Project: settings.gradle and java-library core

For Gradle, replace the POMs and `layers.xml` with the following Groovy DSL files.

### 7.1. Root settings.gradle

~~~groovy
rootProject.name = 'layered-demo'
include 'core', 'app'
~~~

This is a complete `settings.gradle` file. It places **`:core`** and **`:app`** in the same Gradle build. There is no need to apply the Spring Boot Plugin to the root.

### 7.2. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
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
~~~

This is a complete Gradle file for `core`. The Java Library Plugin produces a plain `jar` with library classes at normal classpath locations. `core` does not need the Spring Boot plugin or `bootJar`.

### 7.3. Complete app/build.gradle

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

tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('application')
        }

        dependencies {
            intoLayer('internal-modules') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('internal-releases') {
                include 'com.example:*'
            }
            intoLayer('dependencies')
        }

        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'internal-releases',
            'snapshot-dependencies',
            'internal-modules',
            'application'
        ]
    }
}
~~~

**Key points to remember about Gradle:**

1. `implementation project(':core')` is a dependency within the current build, not `com.example:core:1.0.0` fetched from a Maven repository.
2. `tasks.named('bootJar')` configures the **executable Spring Boot JAR**; configuring only `tasks.named('jar')` will not govern the deployable output.
3. `includeProjectDependencies()` claims `core` before SNAPSHOT and `com.example:*` matchers run.
4. `include 'com.example:*'` is a dependency coordinate pattern inside `dependencies`; it is **not** a filename glob.
5. `include 'org/springframework/boot/loader/**'` belongs in `application`, using path matching to claim loader classes.
6. `layerOrder` lists every layer created by the rules.
7. Source classes and dependency libraries **are not moved out of `BOOT-INF`** inside the executable JAR just by naming layers.
8. `java.toolchain` requires a Java 17 toolchain; the Gradle runtime must also be compatible with the Spring Boot Gradle Plugin and Gradle version.

### 7.4. Running the Gradle Build

From the `layered-demo/` root, with a compatible Gradle Wrapper:

~~~bash
./gradlew :app:clean :app:bootJar
~~~

Or if you want to run the test lifecycle as well:

~~~bash
./gradlew clean build
~~~

Expected executable artifact:

~~~text
app/build/libs/app-1.0.0.jar
~~~

Run:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Stdout line from the application:

~~~text
LAYERING_OK:SKU-42
~~~

Gradle may also produce `app-1.0.0-plain.jar` when running `build`. **Do not use the plain JAR** to test `jarmode=tools` or inspect the Spring Boot layer index.

## 8. Separating Local Projects from Published Internal Libraries

An organization's in-house library can be consumed by the app in two ways.

**Option A: project dependency (local build)**

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

**Option B: published dependency**

~~~groovy
dependencies {
    implementation 'com.example:core:1.0.0'
}
~~~

These are **two mutually exclusive fragments**; never declare both just to demonstrate layered packaging. Option B requires `repositories` capable of resolving those coordinates.

With **Option A**, the `includeProjectDependencies()` matcher claims `core` into `internal-modules`.

With **Option B**, `includeProjectDependencies()` no longer claims `core`. If the version is `1.0.0` and the `com.example:*` matcher runs after the SNAPSHOT rule, `core` enters `internal-releases`. If the version contains `SNAPSHOT`, it can enter `snapshot-dependencies`. Without a company group matcher, it can enter `dependencies` as an external release.

Maven has an analogous situation:

- `mvn -pl app -am ...` from the reactor root: `core` belongs to the build's modules and is claimed by `includeModuleDependencies`.
- `mvn -f app/pom.xml ...` when `core` is resolved only via local/remote repositories: `core` may be treated as a regular dependency. It can go to `internal-releases` via the `com.example:*` group matcher.

**Seeing the same `core-1.0.0.jar` filename does not prove two builds have the same layer assignment.** Inspect `layers.idx` of the final artifact produced by the exact build command you use.

### 8.1. Composite Builds and Substitutions

Gradle included/composite builds have dependency substitution mechanics, so a resolved component can be a project component instead of an external module. If an app uses a composite build, do not guess layer membership from a single `implementation 'com.example:core:1.0.0'` line. Inspect the resolved dependency graph and actual `layers.idx`.

### 8.2. Internal Does Not Always Mean Stable

A company library with a fixed release version that rarely changes can be placed early for caching. However, an internal library frequently published as a **SNAPSHOT** requires a different policy. `internal-releases` in this lesson represents **controlled-version release libraries**, without guaranteeing every artifact under `com.example` is immutable. Use immutable release repositories and dependency locking/verification when needed.

## 9. Inspecting the JAR and Reading BOOT-INF/layers.idx

**The most important QA step** is reading the actual output.

Maven:

~~~bash
jar tf app/target/app-1.0.0.jar
~~~

Gradle:

~~~bash
jar tf app/build/libs/app-1.0.0.jar
~~~

The entry list must contain at least these matching paths:

~~~text
BOOT-INF/layers.idx
BOOT-INF/lib/core-1.0.0.jar
BOOT-INF/classes/com/example/app/LayeredApplication.class
~~~

Many other JARs and resources exist. The mere presence of `BOOT-INF/layers.idx` does not prove `core` landed in the desired layer.

If the system has `unzip`, read the entry directly:

~~~bash
unzip -p app/target/app-1.0.0.jar BOOT-INF/layers.idx
~~~

Or with Gradle:

~~~bash
unzip -p app/build/libs/app-1.0.0.jar BOOT-INF/layers.idx
~~~

Look for `internal-modules` containing **`BOOT-INF/lib/core-1.0.0.jar`**. In an example using only `core` and the Spring Boot starter, `internal-releases` may be empty. This is **not a failure**: do not assume the archive contains a published company dependency when the POM/Gradle build does not declare one.

### 9.1. Two Independent Checks

Success requires both:

1. **Runtime membership:** `jar tf` shows `core-1.0.0.jar` actually exists under `BOOT-INF/lib`.
2. **Layer membership:** `layers.idx` assigns that path to **`internal-modules`**, not merely having a layer header of that name.

If `core` is physically missing, fix dependency declarations/`runtimeClasspath`. If `core` is present yet in the wrong layer, fix **matchers**, **matcher order**, or resolution mode (local project vs. repository).

### 9.2. Do Not Read layers.idx from the Wrong JAR

When Gradle generates both `app-1.0.0.jar` and `app-1.0.0-plain.jar`, pick **`bootJar`**. With Maven, the original JAR prior to repackage may be saved with a **`.original`** extension; do not inspect that file as the executable artifact. A pipeline using globs like **`build/libs/*.jar`** or **`target/*.jar`** can pick the wrong file when multiple artifacts exist.

## 10. Spring Boot 3.3 Tools Mode and Extraction

Spring Boot 3.3 bundles **`spring-boot-jarmode-tools`** when a layered JAR is built with default configuration. Tools mode supports listing layers and extracting into a layout convenient for container images.

### 10.1. Listing Layers

Maven:

~~~bash
java -Djarmode=tools -jar app/target/app-1.0.0.jar list-layers
~~~

Gradle:

~~~bash
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar list-layers
~~~

Actual output depends on the archive file. Listed layers follow the configuration and may be affected if a layer has no contents. **Also read `layers.idx` to confirm `core` membership**; calling `list-layers` alone is not enough.

### 10.2. Extracting by Layer

Maven:

~~~bash
java -Djarmode=tools -jar app/target/app-1.0.0.jar extract --layers --destination extracted
~~~

Gradle:

~~~bash
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar extract --layers --destination extracted
~~~

These commands create the `extracted` directory for use in container builds. In Spring Boot 3.3, tools mode is designed to generate a **small launcher JAR `application.jar`** referencing extracted dependencies alongside the layer directories. Do not assume the internal layout of `extracted/internal-modules` matches the pre-extraction `BOOT-INF/lib` path; inspect the actual output, especially across version upgrades.

**On versions:** Older docs use `-Djarmode=layertools` with different syntax; this lesson targets Spring Boot 3.3 and therefore uses `-Djarmode=tools`, `list-layers`, and `extract --layers`.

**Limitations:** Tools mode does not work with **fully executable** archives having a prepended launch script. If the plugin sets `includeTools=false` or Gradle sets `includeTools=false`, tools mode is also absent by default. In those cases, change packaging configuration or use a different extraction method.

### 10.3. Output Directory Safety

Run extraction inside an appropriate workspace/CI directory; do not let it overwrite important project folders. When rebuilding in the same place, delete **specifically the `extracted` directory that the job just created** using a safe tool rather than running recursive deletion on an unverified path.

## 11. Java 17 Verifier Checking Layer Order and Core Membership

So CI does not rely only on manual reading, use a standalone Java 17 program. It opens the executable JAR via **`JarFile`**, reads `BOOT-INF/layers.idx`, parses layer entries in the format generated by Spring Boot 3.3, verifies layer names/order, and confirms `core-1.0.0.jar` belongs to **`internal-modules`**.

Create `LayerIndexVerifier.java` at the **`layered-demo` root**, outside the main sources of `app` or `core`.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;

public class LayerIndexVerifier {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java LayerIndexVerifier.java <app-jar>");
        }

        List<String> expectedOrder = List.of(
                "dependencies",
                "spring-boot-loader",
                "internal-releases",
                "snapshot-dependencies",
                "internal-modules",
                "application");

        try (JarFile jar = new JarFile(args[0])) {
            ZipEntry entry = jar.getEntry("BOOT-INF/layers.idx");
            if (entry == null) {
                throw new IllegalStateException("Missing layers.idx");
            }

            String content = new String(
                    jar.getInputStream(entry).readAllBytes(),
                    StandardCharsets.UTF_8);

            Map<String, List<String>> layers =
                    new LinkedHashMap<>();
            String currentLayer = null;

            for (String line : content.split("\\R")) {
                if (line.startsWith("- \"")
                        && line.endsWith("\":")) {
                    currentLayer =
                            line.substring(3, line.length() - 2);
                    if (layers.putIfAbsent(
                            currentLayer, new ArrayList<>()) != null) {
                        throw new IllegalStateException(
                                "Duplicate layer: " + currentLayer);
                    }
                } else if (line.startsWith("  - \"")
                        && line.endsWith("\"")) {
                    if (currentLayer == null) {
                        throw new IllegalStateException(
                                "Entry without layer");
                    }
                    layers.get(currentLayer).add(
                            line.substring(5, line.length() - 1));
                }
            }

            int previous = -1;
            for (String layerName : layers.keySet()) {
                int index = expectedOrder.indexOf(layerName);
                if (index < 0 || index <= previous) {
                    throw new IllegalStateException(
                            "Unexpected order: " + layerName);
                }
                previous = index;
            }

            if (!layers.containsKey("internal-modules")
                    || !layers.containsKey("application")) {
                throw new IllegalStateException(
                        "Missing required custom layers");
            }

            String corePath = "BOOT-INF/lib/core-1.0.0.jar";
            if (!layers.get("internal-modules")
                    .contains(corePath)) {
                throw new IllegalStateException(
                        "core not assigned to internal-modules");
            }

            if (jar.getEntry(corePath) == null) {
                throw new IllegalStateException(
                        "core JAR missing from BOOT-INF/lib");
            }

            String appClass =
                    "BOOT-INF/classes/com/example/app/"
                    + "LayeredApplication.class";
            if (jar.getEntry(appClass) == null) {
                throw new IllegalStateException(
                        "Application class missing");
            }
        }

        System.out.println("LAYER_INDEX_OK");
    }
}
~~~

This is a **complete Java 17 file**, using standard APIs and the **Java source-file launcher**. It does not depend on an external YAML parser; hence it only parses the exact `layers.idx` format produced by Spring Boot in this example and is **not a general-purpose YAML parser**.

**Verification points:**

- `BOOT-INF/layers.idx` exists.
- The order of present layers matches `expectedOrder`.
- `internal-modules` and `application` exist.
- `internal-modules` contains exactly **`BOOT-INF/lib/core-1.0.0.jar`**.
- The archive actually contains the `core` JAR at that path.
- The archive actually contains the application main class.

**Do not require `internal-releases` to contain a dependency**, because the example does not yet declare a published company library. If you change the version or base name of `core`, update `core-1.0.0.jar` in the verifier to match the built artifact. In production, you can parameterize group/module/version names.

### 11.1. Running with Maven

~~~bash
mvn -pl app -am clean package
java LayerIndexVerifier.java app/target/app-1.0.0.jar
~~~

### 11.2. Running with Gradle

~~~bash
./gradlew :app:bootJar
java LayerIndexVerifier.java app/build/libs/app-1.0.0.jar
~~~

When all checks pass, the program prints only:

~~~text
LAYER_INDEX_OK
~~~

If an error occurs, it throws an `IllegalStateException` or corresponding exception and returns a non-zero exit code. Never mark a check as PASS after verifying compilation without reading the final archive.

### 11.3. Separate Runtime Verification

After the verifier, run:

~~~bash
java -jar app/target/app-1.0.0.jar
~~~

or the Gradle version:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Expected business output line:

~~~text
LAYERING_OK:SKU-42
~~~

**`LAYER_INDEX_OK` and `LAYERING_OK:SKU-42` are two separate checks.** An archive can have valid layer metadata yet fail to start due to another missing runtime dependency; conversely, the app can run while the layer index violates policy.

## 12. Multi-Stage Dockerfile: Copying Layers in Cache Order

Place `Dockerfile` at the `layered-demo/` root. This example uses the **Maven-built artifact**. The input must be the successfully built **`app/target/app-1.0.0.jar`** file. Spring Boot 3.3 `jarmode=tools extract --layers` creates layer directories along with an `application.jar` optimized to run from the extracted layout.

~~~dockerfile
FROM eclipse-temurin:17-jre AS extract
WORKDIR /workspace

COPY app/target/app-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract \
        --layers --destination extracted

# Allow copying optional layers that have no dependencies yet.
RUN mkdir -p extracted/internal-releases \
             extracted/snapshot-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extract /workspace/extracted/dependencies/ ./
COPY --from=extract /workspace/extracted/spring-boot-loader/ ./
COPY --from=extract /workspace/extracted/internal-releases/ ./
COPY --from=extract /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extract /workspace/extracted/internal-modules/ ./
COPY --from=extract /workspace/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**This Dockerfile follows the Spring Boot 3.3 tools mode layout.** Because `COPY --from=extract` copies from each extracted layer, the final stage can reuse cache for stable layers; `application.jar` is the launcher JAR generated in the extracted layout, **not the full uber JAR copied in the builder stage**.

How to run:

~~~bash
mvn -pl app -am clean package
docker build -t layered-demo:1.0.0 .
docker run --rm layered-demo:1.0.0
~~~

Output line from the app inside the container:

~~~text
LAYERING_OK:SKU-42
~~~

**If choosing Gradle:** replace the first COPY line in the Dockerfile with:

~~~dockerfile
COPY app/build/libs/app-1.0.0.jar application.jar
~~~

This is a **one-line replacement fragment**; do not keep both in the same Dockerfile. Build Gradle beforehand with `./gradlew :app:bootJar`.

**Conditions for the Dockerfile to work:**

- Artifact is truly a Spring Boot 3.3 executable JAR with tools mode; not a Gradle `-plain.jar`.
- The builder can pull the runtime image and has a compatible JDK/JRE.
- `extract --layers` created the launcher and all directory groups referenced by COPY.
- The `internal-modules` layer actually has content because `core` was claimed.
- All runtime dependencies are copied; adding layer names requires updating the Dockerfile.
- Fully executable launch script is not enabled; tools mode does not support that case.
- CI/pipeline has `docker` and permissions to build/run images.

**Note: Dockerfile COPY uses extracted directories, not the raw `BOOT-INF/lib/core-1.0.0.jar` path inside the original JAR.** Tools extraction layouts may change across Boot versions; when upgrading, read the new version's docs and inspect `extracted/`.

### 12.1. Why Must COPY Order Match layerOrder?

In the JAR, `layerOrder` governs the writing order of layers. In the Dockerfile, **`COPY` instructions govern the order of image filesystem layers**. To optimize caching per policy, maintain the same order:

~~~text
dependencies → spring-boot-loader → internal-releases
             → snapshot-dependencies → internal-modules
             → application
~~~

If `core` changes, COPY steps before `internal-modules` can be reused. If `app` changes, ideally only the last layer changes. However, Docker caching also depends on build context, base image digest, Dockerfile, and build engine. **Do not promise specific cache hit rates before measuring**.

### 12.2. Empty Layers and Docker COPY

In an example with only `core` and Boot starter, `internal-releases`/`snapshot-dependencies` may have no entries yet. The Dockerfile creates two empty directories in the builder so `COPY` does not error out over missing source paths. **That is a Docker build-stage operation**; it does not alter the JAR's manifest/`layers.idx` or introduce new dependencies.

If another custom layer is completely empty and missing from the extracted output, handle it similarly or use conditional Dockerfile logic rather than copying a non-existent path.

### 12.3. Docker Images and Buildpacks Do Not Share the Same Strategy

Spring Boot also offers `spring-boot:build-image` (Maven) and `bootBuildImage` (Gradle), which use Cloud Native Buildpacks. Buildpacks have their own partitioning and caching mechanics. **Do not assume** that the six-COPY Dockerfile in this lesson is applied identically by Buildpacks. When optimizing Buildpacks images, inspect the builder's actual layer metadata and image output.

## 13. Measuring the Effectiveness of Layer Design

A practical experiment can be run across three Git versions:

**A — No code changes:** rebuild from the same source, dependency versions, and toolchain. If artifact bytes are stable, the copied layers have a chance for cache hits.

**B — Change only `app`:** edit the message in `LayeredApplication` without changing `SkuFormatter` or the dependency graph. Expect the `application` layer to change; `dependencies`, `loader`, and `internal-modules` can stay unchanged if artifacts are reproducible.

**C — Change only `core`:** change `SkuFormatter` logic while keeping `app` and external libraries untouched. Expect `internal-modules` to change; `dependencies` and `loader` can be reused. Docker steps **after** `internal-modules` may be affected by the cache chain even if application class bytes did not change.

Measure via build logs (cache hit/miss), Docker history, image layer digests, build duration, and remote cache behavior. Do not look only at `layers.idx` and declare faster image pulls.

### 13.1. Layering and Reproducible Builds Complement Each Other

If `core-1.0.0.jar` changes ZIP timestamps on every build despite unchanged source, the `internal-modules` layer can still miss cache. Pin toolchains/dependencies and configure reproducible archives when stable bytes are genuinely required.

**Right layer != identical bytes != cache hit.** These three assertions must be verified independently.

### 13.2. Avoid Creating Too Many Tiny Layers

One layer per library may backfire: metadata overhead, number of COPY commands, and complexity increase. Grouping dependencies with similar change cadences is a balanced solution. Spring Boot's four default layers are already reasonable for many small apps; add `internal-modules`/`internal-releases` only when a real caching need arises.

## 14. Advanced Cases to Consider

### 14.1. Internal Libraries Across Multiple groupIds

If an enterprise uses both `com.example` and `io.example.platform`, `com.example:*` will not match the second group. You can add another matcher/`intoLayer` or put both patterns in the same layer per policy. Verify **actual dependency coordinates**, not filename substrings.

### 14.2. Internal SNAPSHOT Modules

A local `core` at version `1.0.0-SNAPSHOT` should still land in `internal-modules` if the module/project matcher precedes the SNAPSHOT matcher. Swapping their priority changes membership. Write regression tests whenever the team modifies Maven/Gradle scripts.

### 14.3. Large Multi-Project or Composite Builds

If `core` is a library shared by many apps, group modules by change rate. Composite builds and dependency substitution can make an external coordinate resolve to a project component. Inspect the resolved dependency type and actual archive before asserting which layer it belongs to.

### 14.4. Published Library After a Version Bump

If the app updates `company-utils` from `2.0.0` to `2.1.0`, `internal-releases` changes; earlier `dependencies`/loader layers can be reused. Never try to keep the same old JAR filename while altering bytes: immutable artifact coordinates and cache policies must stay consistent.

### 14.5. Spring Boot Plugin Mistakenly Applied to core

If a library module is packaged as an executable Boot JAR, `core`'s Java classes will not sit at the classpath root. Layer matching cannot fix that problem. The right fix is **plain `java-library`/standard JAR for `core`** and **`bootJar`/`repackage` for `app`**.

### 14.6. Dependency Needed at Runtime Gets Excluded

Do not use exclusions or `compileOnly` to “push a library out of a layer”. A missing runtime library can break the app. Only change **layer assignment** while keeping the dependency graph intact.

## 15. Common Mistakes and How to Fix Them

**1. Catch-all placed before specific matchers.** The first matcher claimed every dependency. Place catch-alls last and re-read `layers.idx`.

**2. Confusing matching order with `layerOrder`.** Matchers determine membership; `layerOrder` determines writing order. Adjust whichever part you actually intend to change.

**3. Treating a published internal library as a local module.** It is not part of the current reactor/project build. Use a GAV matcher and check the resolver context.

**4. Building `app` standalone in Maven while expecting `core` in `internal-modules`.** `-f app/pom.xml` can resolve `core` from the local repo; run `-pl app -am` from root or accept the published-internal policy.

**5. Using coordinates `com.example:core:1.0.0` in Gradle while expecting `includeProjectDependencies` to claim it.** External coordinates are not `project(':core')`. Fix the dependency or matcher.

**6. Local module SNAPSHOT claimed first by the SNAPSHOT matcher.** Change claim order if policy requires separating local modules.

**7. Overly broad group matcher.** A pattern like `*:*` or an early catch-all can swallow all dependencies. Use specific groups and verify each artifact.

**8. Using a path pattern in a `dependencies` matcher.** `BOOT-INF/lib/core*.jar` is not a GAV pattern for the `dependencies` section. Use `com.example:*` or module/project matchers.

**9. Using a GAV pattern in an `application` matcher.** The `application` section uses Ant-style paths. Loader matchers must look like `org/springframework/boot/loader/**`.

**10. Missing `layerOrder` or misspelled layer name.** Custom configs must list all layers. Check spelling/casing.

**11. Configuring only Gradle `jar`.** Executables are built by `bootJar`; place the layered DSL on the right task.

**12. Maven did not run `repackage`.** May produce a plain JAR lacking the index. Check the Boot Maven Plugin and Spring Boot parent execution.

**13. Wrong XML path or schema namespace.** Place `app/src/layers.xml` and use Boot 3.3's `layers-3.3.xsd` schema.

**14. `BOOT-INF/layers.idx` not found.** Verify you chose the executable JAR, layers are enabled, and the plugin ran.

**15. `core` missing from `BOOT-INF/lib`.** Fix the Maven/Gradle dependency graph first; layering never adds an undeclared library to runtime.

**16. `layers.idx` shows `internal-modules` yet omits `core`.** A layer name existing does not guarantee every library was claimed properly. Use a verifier/membership check.

**17. Using legacy `layertools` on Boot 3.3.** Boot 3.3 supports tools mode with `list-layers` and `extract --layers`. Match syntax to version.

**18. Tools mode fails on a fully executable archive.** Do not prepend a launch script when needing tools extraction; check `includeTools` and the build plugin.

**19. Inspecting `app-1.0.0-plain.jar` by mistake.** Plain JARs are not deployable Boot artifacts. Pick `app-1.0.0.jar`.

**20. Dockerfile copies only a few layers.** Omitting `internal-modules` causes runtime to miss `core`. Copy all layers and smoke-test the container.

**21. Dockerfile copies out of policy order.** Fails to maximize caching. Synchronize with `layerOrder`.

**22. Dockerfile uses a launcher command from another version.** Spring Boot 3.3 tools extraction creates a launcher compatible with `java -jar application.jar`; verify with an image smoke test when upgrading versions.

**23. Assuming `extracted/internal-modules` matches `BOOT-INF/lib` from the raw JAR.** Extraction layout differs; inspect actual output and copy the whole layer directory in Dockerfile COPYs.

**24. `internal-releases` rules miss a new group.** Update patterns when company libraries introduce another `groupId`.

**25. Using mutable SNAPSHOTs while expecting stable cache.** Pin and manage artifact versions/checksums according to release policy.

**26. Assuming `layers.idx` changes Java classpath priority.** This is metadata for layer packaging; dependency conflicts must be resolved in the build graph.

**27. Creating many layers yet image does not shrink.** Layering optimizes cache/reuse rather than stripping code/dependencies. Measure size and cache separately.

**28. CI checks only build success.** Must verify the index, `core` membership, and running the real JAR/container.

**29. Packaging `core` as an executable Boot JAR.** Plain libraries are required when `app` needs to import `core` classes.

**30. Measuring cache across two builds with different toolchains/dependencies.** Differing inputs invalidate comparisons against layer policy; standardize before measuring.

## 16. QA Workflow for CI Integration

### Maven

~~~bash
mvn -pl app -am clean package
java LayerIndexVerifier.java app/target/app-1.0.0.jar
java -jar app/target/app-1.0.0.jar
java -Djarmode=tools -jar app/target/app-1.0.0.jar list-layers
~~~

### Gradle

~~~bash
./gradlew :app:clean :app:bootJar
java LayerIndexVerifier.java app/build/libs/app-1.0.0.jar
java -jar app/build/libs/app-1.0.0.jar
java -Djarmode=tools -jar app/build/libs/app-1.0.0.jar list-layers
~~~

These are two alternatives depending on your build system. **Do not run both Maven and Gradle in the same project**.

A CI gate can require:

- Build task exits cleanly with status 0.
- `BOOT-INF/layers.idx` exists.
- Layer names/order align with strategy.
- `BOOT-INF/lib/core-1.0.0.jar` exists.
- `core-1.0.0.jar` resides inside `internal-modules`.
- `LayerIndexVerifier.java` prints `LAYER_INDEX_OK`.
- `java -jar` prints `LAYERING_OK:SKU-42`.
- Docker image smoke test passes when the pipeline uses a custom Dockerfile.
- Upgrades to Boot/Gradle/Maven re-run tests since DSL, schemas, and tools mode can change.

Never mark a build as passing solely on a `BUILD SUCCESSFUL` line; that does not prove custom layers are right.

## 17. Production Deployment Checklist

- [ ] Distinguished **local module/project dependencies** from **published internal dependencies**.
- [ ] Documented clear policy for release/SNAPSHOT libraries and internal `groupId` groups.
- [ ] Placed local module matchers before broader matchers when prioritizing `internal-modules`.
- [ ] Placed catch-all `dependencies` last.
- [ ] Listed every layer name accurately in `layerOrder`.
- [ ] Used a valid `layers.xml` for Maven or proper `bootJar.layered` in Gradle.
- [ ] Did not apply the Boot plugin to library `core` just to build a JAR.
- [ ] Ran builds in the exact same reactor/project context as CI.
- [ ] Used the executable Boot JAR, not a plain JAR.
- [ ] Inspected `layers.idx` of the final archive.
- [ ] Verified `core` membership, not just the layer name.
- [ ] Tested tools mode/`list-layers`/extract on the exact release artifact.
- [ ] Dockerfile copies all extracted layers in proper cache order.
- [ ] Ran app/container smoke tests with a compatible Java runtime.
- [ ] Pinned dependencies and toolchain; used reproducible builds when stable layer bytes are needed.
- [ ] Measured actual cache hits/layer digests rather than claiming gains before measuring.
- [ ] Kept rules and verification synchronized whenever GAVs, module names, versions, or Boot releases change.

## 18. Official References

- Spring Boot 3.3 — Maven Plugin, Layered Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Layered JAR/War: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Dockerfiles, `jarmode=tools` extraction: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3 — Efficient Deployments: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Apache Maven — Multi-module Reactor Guide: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Gradle 8.5 — Multi-project Builds: https://docs.gradle.org/8.5/userguide/multi_project_builds.html
- Docker — Build Cache: https://docs.docker.com/build/cache/
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Conclusion:** In Spring Boot layered archives, **matcher order determines which layer a library belongs to**, while **`layerOrder` determines layer order for images/caching**. Maven recognizes local modules from the **current reactor**, and Gradle recognizes local modules from **project dependencies**; published internal libraries require dedicated GAV matchers if you want to layer them by origin. When using **`internal-modules`** and **`internal-releases`**, verify **`BOOT-INF/layers.idx`**, the actual path of `core`, tools mode extraction, and that the application/container runs. Configuring XML/Groovy without inspecting the final artifact is not enough.