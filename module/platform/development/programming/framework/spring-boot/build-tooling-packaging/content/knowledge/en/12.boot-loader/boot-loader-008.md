# Distinguishing Spring Boot Nested Archives from Merged JARs Built by Maven Shade or Gradle Shadow

## 1. Scope and Objectives

When packaging a Java application into **a single file runnable via `java -jar`**, you may encounter terms like `executable JAR`, `fat JAR`, `uber JAR`, `shaded JAR`, and **Spring Boot executable JAR**. These terms are **not completely synonymous**.

- **Spring Boot executable JAR with default layout:** keeps most dependencies as **nested JAR files inside the main JAR**, typically in `BOOT-INF/lib/`. Spring Boot Loader creates a classloader that can read those nested dependencies.
- **Maven Shade Plugin / Gradle Shadow Plugin:** usually **opens dependency JARs**, merging `.class` files and resources into **the same directory namespace of a single combined JAR** (uber/shaded JAR). Merging can involve resource merging, package relocation, and duplicate-handling steps.

Both can yield **a single file for release**, yet their **layout, classloading, manifest, dependency inspectability, and resource collision risks differ**.

After this lesson, you will be able to:

1. Accurately identify archive types from `jar tf` and `META-INF/MANIFEST.MF`.
2. Explain Spring Boot's `BOOT-INF/classes`, `BOOT-INF/lib`, `JarLauncher`, and `Start-Class`.
3. Distinguish Boot Loader's mechanism from Shade/Shadow's bytecode merging.
4. Build a **Spring Boot nested JAR**, a **Maven shaded JAR**, and a **Gradle shadow JAR** using separate examples with verifiable run commands and outputs.
5. Understand `META-INF/services`, Spring auto-configuration metadata, resource collisions, relocation, signature files, and the impact of minimization.
6. Know when to prefer Boot `bootJar`/`repackage` and when to use Shade or Shadow for a CLI tool/library.
7. Avoid combining Boot repackage with shade on the same artifact or confusing "one JAR" with "identical internal structure".

**Illustrative versions:** Java 17+, Spring Boot `3.5.16`, Apache Commons Lang `3.17.0`, Maven Shade `3.6.2`, Shadow `9.3.0`. These are **specific coordinates to illustrate and reproduce the examples**, not a requirement for every project to upgrade to these versions. Shadow `9.3.0` requires at least **Gradle 9.0** and Java 17 per GradleUp's compatibility matrix. Check versions supported by your project/CI before copying configurations.

## 2. "Fat JAR" Describes Distribution Capability, Not a Single Layout

Many teams call both Boot executable JARs and shaded JARs **fat JARs** because both carry the dependencies needed to run. A more accurate way to tell them apart is **inspecting the internal structure**.

### 2.1. Regular/Library JAR (Thin JAR)

~~~text
plain-app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/app/
    └── App.class
~~~

A regular JAR usually contains only the project's own classes/resources. External dependencies **are not automatically embedded** just because they appear in `pom.xml` or `build.gradle`. To run, it needs a proper classpath or a separate dependency distribution mechanism. Having `Main-Class` does not make it a self-contained archive if required libraries are missing from the classpath.

### 2.2. Spring Boot Nested Executable JAR

~~~text
nested-boot-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/archives/NestedBootApplication.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   ├── commons-lang3-3.17.0.jar
    │   └── ...
    ├── classpath.idx                  # may be present
    └── layers.idx                     # may be present
~~~

The `BOOT-INF/lib/*.jar` files remain **separate JARs** stored as entries of the outer ZIP/JAR. Commons Lang's class does not appear directly at the root path `org/apache/commons/lang3/StringUtils.class` in **the outer JAR**; it sits **inside** the `commons-lang3-3.17.0.jar` entry.

Spring Boot Loader is a specialized startup program using an appropriate classloader to find app classes in `BOOT-INF/classes` and dependency classes in nested JARs. The standard JVM **does not automatically add nested JARs to the classpath** if given only a regular `-cp outer.jar`.

### 2.3. Maven Shaded or Gradle Shadow JAR

~~~text
flat-app-1.0.0-all.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/...
├── com/example/archives/
│   └── App.class
├── org/apache/commons/lang3/
│   └── StringUtils.class
└── ... many merged classes/resources ...
~~~

Here dependency classes are **unpacked and placed into the root classpath namespace of the same JAR**. No Spring Boot Loader is needed to find `org.apache.commons.lang3.StringUtils` because the class file is already present as a normal entry. If the archive manifest has `Main-Class: com.example.archives.App` and all dependencies are present, the standard JVM launcher can run it via `java -jar`.

**Emphasis:** merging **does not automatically resolve** duplicate filenames, SPI configurations, reflection, or version incompatibilities. Shade and Shadow provide tools to handle these situations, yet configuration responsibility remains with the project.

## 3. Technical Comparison Table

| Aspect | Spring Boot nested executable JAR | Maven Shade / Gradle Shadow |
| --- | --- | --- |
| How dependencies are stored | Separate JARs in `BOOT-INF/lib/` | Classes/resources from dependencies usually merged into main JAR |
| App classes | `BOOT-INF/classes/` | Root package paths like `com/example/...` |
| Typical Main-Class | `org.springframework.boot.loader.launch.JarLauncher` | Application's `main` class |
| Start-Class | Records application main class in manifest | Does not need Boot Loader's `Start-Class` convention |
| Classloader | Spring Boot Loader supporting nested JARs | Standard Java classpath/JAR loading for merged file |
| Visibility of individual dependency JARs | JAR names and boundaries remain clear | Original JAR boundaries are merged, hard to distinguish from `jar tf` alone |
| Colliding resources at same path | Keeps files in separate JARs; classloader can look up resources | Must pick/merge/transform to avoid data loss |
| Package relocation | Not the primary goal of `repackage` | Shade/Shadow support relocation per configuration |
| `META-INF/services` | Preserves descriptors in respective JARs | Usually requires merging service descriptors |
| Container layer optimization | Has `layers.idx` and suitable Boot tooling | Does not automatically include Boot `layers.idx` |
| Use as library dependency | Executable JAR unsuitable for direct use as thin library | Shaded library can be used, though relocation/API require control |
| Maven build | Spring Boot Maven Plugin `repackage` | Maven Shade Plugin `shade` |
| Gradle build | Spring Boot Gradle Plugin `bootJar` | GradleUp Shadow Plugin `shadowJar` |

Both styles can fail if dependencies are missing or versions conflict. The table describes **packaging structure and behavior**, without promising that one approach is always smaller, faster, more secure, or easier to deploy across every project.

## 4. What Does Spring Boot Loader Actually Do?

### 4.1. Java Launcher Only Reads the Outer Main-Class

When running:

~~~bash
java -jar nested-boot-0.0.1-SNAPSHOT.jar
~~~

the Java launcher reads `META-INF/MANIFEST.MF` of the outer JAR to get `Main-Class`. For a Boot executable JAR of `JAR` layout in the 3.5 line, a typical manifest is:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.archives.NestedBootApplication
Spring-Boot-Version: 3.5.16
~~~

This **illustrates the relevant manifest attributes**, without guaranteeing the actual manifest has only four lines. The Spring Boot Maven/Gradle plugin may add extra metadata.

Execution flow:

~~~text
java -jar app.jar
    |
    v
MANIFEST.MF : Main-Class = JarLauncher
    |
    v
Boot Loader locates BOOT-INF/classes and BOOT-INF/lib/*.jar
    |
    v
Creates appropriate classloader for nested JAR entries
    |
    v
MANIFEST.MF : Start-Class = application main
    |
    v
com.example.archives.NestedBootApplication.main(args)
    |
    v
SpringApplication.run(...)
~~~

Spring Boot has `WarLauncher` for executable WARs, `PropertiesLauncher` in appropriate layouts, and other loader mechanisms by version. **Launcher package names changed between older and newer Boot lines**; for instance, `org.springframework.boot.loader.launch.JarLauncher` is for Boot 3.5 — do not copy from Boot 2.x guides into a 3.x manifest without checking.

### 4.2. Why Doesn't the Normal JVM Automatically Load JARs Inside a JAR?

A `JAR` essentially uses the ZIP format. The standard Java classpath knows how to find classes from directories or JARs placed on the classpath, but **defines no mechanism to traverse every JAR inside a JAR and add each to the classpath**. Boot Loader implements reading nested archives, building the loader/classpath, and invoking the application entry point.

Therefore:

~~~bash
# Right for a Boot executable JAR per manifest:
java -jar nested-boot-0.0.1-SNAPSHOT.jar
~~~

is not equivalent to:

~~~bash
# Do not assume standard JVM understands BOOT-INF/lib/ when running -cp:
java -cp nested-boot-0.0.1-SNAPSHOT.jar \
  com.example.archives.NestedBootApplication
~~~

The second command will not automatically look in `BOOT-INF/classes` and nested dependency JARs per the default layout. It may fail with `ClassNotFoundException` or missing dependencies.

### 4.3. Nested JAR Entries and Compression Method

Per Boot's executable JAR specification, nested JAR entries in the outer archive must be written with ZIP method **`STORED`** (the outer entry itself is uncompressed). This allows Boot Loader to seek/locate content inside the nested archive directly. **Inside the nested dependency JAR**, entries can remain normally compressed; `STORED` applies only to **the entry representing the entire nested JAR** in the outer archive.

If you open and re-zip a Boot executable JAR with a tool that does not preserve the proper storage method for nested entries, the archive may **fail to run**, even though `jar tf` still lists it. Do not replace the standard packaging step of the Boot Maven/Gradle plugin with an unverified manual ZIP script.

### 4.4. Classloader and Third-Party Libraries

Applications running under Boot Loader typically rely on libraries fetching resources/classes via the **thread context classloader** when appropriate. Some libraries using `ClassLoader.getSystemClassLoader()` or assuming every dependency is a separate file path directly on disk may not behave as they do in an IDE.

Do not declare a library broken from an API name alone: run an integration test on the actual executable JAR. Some libraries require unpacking, and the Spring Boot Maven Plugin supports `requiresUnpack` for suitable cases; do not extract all dependencies as a default "fix".

## 5. Example A — Building a Spring Boot Nested Executable JAR

This is a **standalone** project to clearly see the Boot Loader layout. The project **needs no web server**, printing just one line upon successful startup. The example uses Commons Lang so learners see a dependency JAR kept intact under `BOOT-INF/lib`.

### 5.1. Directory Structure

~~~text
nested-boot/
├── pom.xml
└── src/main/java/com/example/archives/
    └── NestedBootApplication.java
~~~

If created via Spring Initializr, `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/` are also present. If creating only the two files above, use an installed Maven with `mvn`.

### 5.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>nested-boot</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
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

The Spring Boot starter parent in this example already configures the `repackage` execution. Thus Maven `package` produces an executable JAR with Boot Loader; you **do not need to add the Maven Shade Plugin**. If a real project uses its own corporate parent, a BOM import does not inherit this plugin management/execution; you must declare `spring-boot-maven-plugin` + version + `repackage` goal properly.

### 5.3. Java 17+ Source

Create `src/main/java/com/example/archives/NestedBootApplication.java`:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NestedBootApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedBootApplication.class, args);
    }

    @Bean
    ApplicationRunner showArchiveType() {
        return args -> System.out.println(
                "BOOT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

This is the complete Java source of the Spring Boot application. `@Bean ApplicationRunner` executes once the context is initialized. `StringUtils.capitalize("hello")` returns `Hello`, so the exact verifiable line **printed by application code** is:

~~~text
BOOT_OK Hello
~~~

Spring Boot also emits startup logs (timestamps, logger, environment varying by machine), so **do not claim total stdout** contains only this single line.

### 5.4. Build and Run

From the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn clean package
java -jar target/nested-boot-0.0.1-SNAPSHOT.jar
~~~

If the project has Maven Wrapper:

~~~bash
./mvnw clean package
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
java -jar .\target\nested-boot-0.0.1-SNAPSHOT.jar
~~~

Only use the Wrapper commands if `mvnw`/`mvnw.cmd` **actually exist in the project**. Building requires a JDK 17+ compatible with Spring Boot and network/repository access if dependencies are not yet cached.

### 5.5. Verify the Archive

~~~bash
jar tf target/nested-boot-0.0.1-SNAPSHOT.jar
~~~

Look for representative entries:

~~~text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/archives/NestedBootApplication.class
BOOT-INF/lib/commons-lang3-3.17.0.jar
BOOT-INF/lib/spring-boot-*.jar
~~~

The `*` on the last line **illustrates a group of JAR names with varying versions**, not a literal path guaranteed in `jar tf`.

Do not expect outer `jar tf` to display:

~~~text
org/apache/commons/lang3/StringUtils.class
~~~

because that class resides **inside** `BOOT-INF/lib/commons-lang3-3.17.0.jar`, not at the outer archive root.

Read the manifest on Linux/macOS if `unzip` is available:

~~~bash
unzip -p target/nested-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
~~~

The key output lines are `Main-Class: org.springframework.boot.loader.launch.JarLauncher` and `Start-Class: com.example.archives.NestedBootApplication`. On Windows without `unzip` installed, you can open the JAR as a ZIP in an archive viewer and inspect `META-INF/MANIFEST.MF` read-only; never repack the archive manually.

## 6. Maven Shade: Merging Classes and Resources into an Uber JAR

### 6.1. What Does Maven Shade Plugin Do?

`maven-shade-plugin` provides the `shade` goal; typically it takes the project's classes/resources and resolved runtime dependencies, **unpacks and merges** them into the resulting JAR. Notable features:

- `ManifestResourceTransformer` to set `Main-Class` (and other manifest entries).
- `ServicesResourceTransformer` to merge `META-INF/services/*` and update provider names when relocation applies.
- `relocations` to rename class packages to avoid classpath conflicts.
- `filters` to specify resource/metadata includes/excludes, such as signatures invalidated by merging.
- `shadedArtifactAttached` and `shadedClassifierName` to retain the regular artifact while also attaching a shaded variant with its own classifier.

**Shade is not Spring Boot Loader.** In the next example, we intentionally use a **pure Java CLI project** to demonstrate a shaded JAR running via the standard JVM without any nested-dependency lookup mechanism.

### 6.2. Separate Shade Project Structure

~~~text
flat-maven/
├── pom.xml
└── src/main/java/com/example/archives/
    └── App.java
~~~

File `App.java`:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {}

    public static void main(String[] args) {
        System.out.println(
                "FLAT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

This is complete Java 17+ source. When run successfully with Commons Lang on the classpath, stdout is **exactly**:

~~~text
FLAT_OK Hello
~~~

### 6.3. Complete pom.xml for Maven Shade

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>flat-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>com.example.archives.App</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:

- `maven-compiler-plugin` configures compiling for Java 17.
- `shade` runs during the `package` phase after Maven Jar Plugin builds the project's normal JAR in the lifecycle.
- `shadedArtifactAttached=true` and classifier `all` produce a **separate shaded artifact**, normally `target/flat-maven-1.0.0-all.jar`. The regular `target/flat-maven-1.0.0.jar` still exists and **does not bundle Commons Lang inside**.
- `createDependencyReducedPom=false` disables generating `dependency-reduced-pom.xml` in this simple app example. For published libraries, this choice affects dependency metadata/POMs and requires dedicated design.
- `ManifestResourceTransformer` sets `Main-Class: com.example.archives.App` for direct JVM execution.
- `ServicesResourceTransformer` handles Java SPI service descriptors at colliding paths. The example only uses Commons Lang so it does not rely on this transformer for its stdout; it is included to demonstrate best practice for multi-dependency applications.

**Do not add `spring-boot-maven-plugin` to this Shade project** just to get `java -jar`. Maven Shade already generates an executable manifest. If building a genuine Spring Boot application, defaulting to the Boot plugin with nested layout carries far less risk of breaking resources/auto-configuration.

### 6.4. Build, Run, and Inspect

~~~bash
mvn clean package
java -jar target/flat-maven-1.0.0-all.jar
jar tf target/flat-maven-1.0.0-all.jar
~~~

In the shaded JAR, look for:

~~~text
META-INF/MANIFEST.MF
com/example/archives/App.class
org/apache/commons/lang3/StringUtils.class
~~~

With the example config, there is **no need for** and normally **no** `BOOT-INF/lib/commons-lang3-3.17.0.jar` or Boot `JarLauncher`. Read the manifest:

~~~bash
unzip -p target/flat-maven-1.0.0-all.jar META-INF/MANIFEST.MF
~~~

Important value:

~~~text
Main-Class: com.example.archives.App
~~~

Program output:

~~~text
FLAT_OK Hello
~~~

**Do not accidentally run the thin JAR** `target/flat-maven-1.0.0.jar` and blame Shade: that is a different output. The thin JAR may lack `Main-Class`, or even if given a manifest, will still lack runtime dependencies without an external classpath.

## 7. Gradle Shadow: Same Principle as Maven Shade

### 7.1. GradleUp Shadow Builds Uber JARs

Gradle Shadow (currently maintained under plugin ID `com.gradleup.shadow`) creates the `shadowJar` task when applied alongside Java/Kotlin JVM/Groovy plugins. By default `shadowJar` merges project classes/resources with `runtimeClasspath` dependencies using classifier `all`, rather than Spring Boot's nested JAR format.

The legacy plugin ID `com.github.johnrengelman.shadow` may appear in older repositories. For new projects, use plugin ID `com.gradleup.shadow` compatible with the project's Gradle/Java versions.

The next example uses the same `App.java` as Maven Shade in Section 6; only the build tool changes. **Do not place a Maven POM and Gradle build in the same lab directory and run both in one project** without understanding which source of dependencies/artifacts is authoritative.

### 7.2. Separate Gradle Project Structure

~~~text
flat-gradle/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/archives/
    └── App.java
~~~

Contents of `settings.gradle`:

~~~groovy
rootProject.name = 'flat-gradle'
~~~

Create `App.java` identically to Section 6.2:

~~~java
package com.example.archives;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {}

    public static void main(String[] args) {
        System.out.println(
                "FLAT_OK " + StringUtils.capitalize("hello"));
    }
}
~~~

### 7.3. Complete build.gradle — Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'com.gradleup.shadow' version '9.3.0'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('shadowJar') {
    archiveBaseName.set('flat-gradle')
    archiveClassifier.set('all')
    manifest {
        attributes 'Main-Class': 'com.example.archives.App'
    }
}
~~~

Explanation:

- The `java` plugin provides `compileJava`, `jar`, `test`, and standard Java project mechanics.
- `com.gradleup.shadow` provides `shadowJar`, which merges dependencies from `runtimeClasspath` by default.
- `toolchain Java 17` selects a compatible compiler if the JDK/toolchain is available/provisioned.
- `archiveClassifier='all'` distinguishes the shaded artifact from the thin `jar`.
- `manifest Main-Class` invokes `App.main` directly via the standard launcher, **no Boot JarLauncher needed**.

With Shadow `9.3.0`, use **Gradle 9.0+** and Java 17+ to run the Gradle plugin. Do not copy this version into a project locked to Gradle 8.x; substitute a Shadow version compatible per the official compatibility matrix. **Do not assume** installing JDK 17 is enough for every Gradle version: check `gradle -version` too.

### 7.4. Build and Run Across Operating Systems

With Gradle installed:

~~~bash
gradle shadowJar
java -jar build/libs/flat-gradle-1.0.0-all.jar
jar tf build/libs/flat-gradle-1.0.0-all.jar
~~~

If the project has a Gradle Wrapper generated via `gradle wrapper`:

~~~bash
./gradlew shadowJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat shadowJar
java -jar .\build\libs\flat-gradle-1.0.0-all.jar
~~~

Just like Maven Shade, expected stdout is:

~~~text
FLAT_OK Hello
~~~

And representative entries include:

~~~text
com/example/archives/App.class
org/apache/commons/lang3/StringUtils.class
META-INF/MANIFEST.MF
~~~

`BOOT-INF/lib/commons-lang3-3.17.0.jar` **is not** how Shadow normally packages dependencies in this output. If you see intact nested JARs inside the output, check task inputs and any custom `from(...)`/`zipTree(...)` configurations.

### 7.5. Gradle bootJar Differs from shadowJar

In a **Spring Boot Gradle project**, the Boot plugin uses the `bootJar` task to build a nested executable Boot archive. In a **Java + Shadow project** like the example, the `shadowJar` task builds a merged JAR.

When applying both the Boot Gradle plugin and Shadow together, both tasks can coexist, yet **outputs must not arbitrarily overwrite the same path**. Clearly define:

- Which task produces the primary deployable artifact.
- Archive names/classifiers of `bootJar` and `shadowJar`.
- Which task CI/CD runs and which artifact is published.
- Which tests run against the actual production artifact.

Never instinctively use `zipTree(bootJar.archiveFile)` and merge more dependencies to "turn a Boot JAR into a shaded JAR": the Boot JAR already has `BOOT-INF` and its own loader layout; you could end up with an archive having two overlapping classpath mechanisms or a broken manifest.

## 8. The Big Problem with Merged JARs: Colliding Resource Names

### 8.1. Why Merging Classes Alone Is Not Enough

Many Java libraries share **the same resource file paths**:

~~~text
library-a.jar: META-INF/services/com.example.spi.Plugin
library-b.jar: META-INF/services/com.example.spi.Plugin
~~~

Each file lists one or more implementations of the same Java SPI. When shading, if you only keep the first (or last) file at a colliding path, `ServiceLoader` **loses some providers**. When nested JARs stay separate, the classloader can read resource descriptors from separate dependencies to aggregate providers according to standard rules.

Similarly, Spring Framework/Spring Boot rely on many special resources under `META-INF/`. Merging mechanisms must understand **the format and semantics** of each resource rather than arbitrarily picking the first file.

### 8.2. Maven Shade: ServicesResourceTransformer

Snippet in `maven-shade-plugin`:

~~~xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>com.example.archives.App</mainClass>
    </transformer>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

`ServicesResourceTransformer` merges `META-INF/services/*` files and updates related provider class names when relocation is used. **It does not automatically merge every configuration type**, such as JSON, properties, or Spring auto-configuration imports. Other transformers exist (like `AppendingTransformer`), yet choosing the wrong format can render metadata invalid.

### 8.3. Gradle Shadow: mergeServiceFiles and Duplicate Strategy

With Shadow `9.x`, pay attention to **`duplicatesStrategy`**: if `EXCLUDE` is set too broadly/early, colliding service descriptors may be dropped **before the transformer runs**, preventing `mergeServiceFiles()` from seeing all inputs.

When merging service descriptors is needed, you can configure `build.gradle` (snippet inside a Java + Shadow project):

~~~groovy
tasks.named('shadowJar') {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()

    filesNotMatching('META-INF/services/**') {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}
~~~

Idea: **keep all colliding descriptors for the transformer to process**, without accidentally letting all other duplicate resources into the output. In complex projects, audit other collisions too, especially license/notice, properties, Spring metadata, and signature files. Do not set `INCLUDE` globally while ignoring warnings/duplicate entries.

In Shadow `9.x`, duplicate strategy behavior saw changes across minor versions; always consult the docs for your exact version, check build logs, and consider enabling `failOnDuplicateEntries` once a resource handling strategy is settled.

### 8.4. Spring Boot Auto-Configuration Metadata

Spring Boot 3.x uses resources of the form:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

to list auto-configuration classes from dependencies. The Spring ecosystem can also use `META-INF/spring.factories`, `META-INF/spring.handlers`, `META-INF/spring.schemas`, and other metadata.

When Shade/Shadow merges a Boot app without an appropriate merge strategy, **some auto-configurations or factories can vanish**, causing the application to start missing beans, missing converters, or failing unexpectedly at runtime.

**`mergeServiceFiles()` only handles `META-INF/services`**, and does not automatically make all Spring resources valid. If forced to shade a Spring Boot app, design transformers for every resource format, test full startup/critical flows, and inspect the final artifact. For typical Spring Boot apps, **Boot nested packaging is the safer default**, because it preserves dependency boundaries and metadata the way Boot runtime expects.

### 8.5. META-INF/MANIFEST.MF and JAR Signatures

A dependency JAR may contain signature files such as:

~~~text
META-INF/SOMELIB.SF
META-INF/SOMELIB.RSA
META-INF/SOMELIB.DSA
~~~

When Shade/Shadow unpacks and modifies archive contents, the original dependency's signature **no longer matches the merged JAR's bytes**. Keeping original signatures can cause `SecurityException: Invalid signature file digest for Manifest main attributes` at runtime.

Maven Shade can strip invalid signature files using `filters`, such as this snippet inside `<configuration>` of the plugin:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
        </excludes>
    </filter>
</filters>
~~~

This is how signature metadata is handled **when merging JARs**, not advice to skip verifying dependency sources. Continue verifying dependency artifacts before the build, generate SBOMs/checksums/signed release artifacts per team policy, and retain required licenses/notices. Shadow excludes JAR signatures and JAR indexes by default as documented; still verify your plugin version and actual output.

## 9. Relocation: A Feature of Shade/Shadow, Not Nested Packaging

### 9.1. What Is Relocation?

Suppose plugin/library A and the application both need a library with package `org.example.util` at two incompatible versions. Maven Shade or Shadow can **rename packages/classes** of a dependency **during packaging**, for example:

~~~text
Before: org.example.util.Helper
After:  com.acme.internal.shaded.util.Helper
~~~

The goal is reducing namespace collisions on the **consumer's** classpath. This is especially useful when publishing a library/plugin used in environments with many hard-to-control dependencies.

**Relocation is not a version upgrade**; it rewrites bytecode class references and some resource descriptors within the tool's capabilities. Renaming class packages can affect **reflection, serialized class names, resource lookups, ServiceLoader, JNI, module-info, frameworks scanning class names as strings**, etc.

### 9.2. Illustrative Maven Shade Relocation

In `maven-shade-plugin`, under `<configuration>`:

~~~xml
<relocations>
    <relocation>
        <pattern>org.apache.commons.lang3</pattern>
        <shadedPattern>com.example.internal.shaded.lang3</shadedPattern>
    </relocation>
</relocations>
~~~

If applied to the CLI demo, `StringUtils` in the **output** may reside at the new path, and `App.class` bytecode is rewritten by the plugin to reference the new name. **Java source still imports** the original package when compiling; relocation happens during packaging.

### 9.3. Illustrative Gradle Shadow Relocation

In `build.gradle`, inside the `shadowJar` task:

~~~groovy
tasks.named('shadowJar') {
    relocate 'org.apache.commons.lang3',
             'com.example.internal.shaded.lang3'
}
~~~

Both snippets are **additional configuration examples**, not required for the three baseline projects. For a Spring Boot app, **never enable broad relocation for `org.springframework.*`**: vast amounts of metadata, reflection, and framework contracts rely on exact class/package names.

### 9.4. Minimization Can Break Runtime Reflection

Shade has `minimizeJar`; Shadow has `minimize()`. Size-reduction mechanisms based on static reference analysis can strip classes **loaded only via reflection, SPI, configuration, Spring DI/auto-configuration, or serialization**. A project can compile and pass unit tests yet throw `ClassNotFoundException` at runtime after minimization.

Rule: **measure actual output, maintain allowlists/exclusions, and run integration/smoke tests** before using minimize on Spring Boot applications or complex plugin frameworks.

## 10. Why Not Enable Both Boot Repackage and Maven Shade on the Same Artifact?

### 10.1. Two Plugins Modifying Structure by Different Rules

If a `pom.xml` binds both `maven-shade-plugin:shade` and `spring-boot-maven-plugin:repackage` to `package` for **the same artifact**, the outcome depends on goal order, classifiers, source JAR replacement, and which files/manifest each plugin writes. You may encounter:

- Boot repackage processing an already-shaded JAR, embedding dependencies both as merged classes and as nested libraries.
- Shade processing a Boot executable JAR, merging files while keeping `BOOT-INF`/loader in an unintended layout.
- `Main-Class` overwritten from `JarLauncher` to the application or vice versa; manifest and file tree no longer align.
- Lost resource descriptors, duplicate classes, and unexpected dependency conflicts.
- CI publishing the wrong `original`/`all`/`exec` classifier, causing production to run a different artifact than tested.

**There is no universal rule that "Shade always runs first and Boot handles the rest".** If two formats are needed, produce **separate artifacts/classifiers or modules**, control tasks/goals per output, avoid overlapping file paths, and smoke-test **the exact file being deployed**.

### 10.2. For Typical Spring Boot Apps: Choose Boot's Standard Plugin

Maven:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

If using `spring-boot-starter-parent`, the `repackage` goal is already configured in the parent; otherwise add an appropriate execution/version.

Gradle when using the Spring Boot plugin:

~~~bash
./gradlew bootJar
~~~

Choose `bootJar` to create a nested executable JAR with Boot loader; do not use `shadowJar` merely because a deployment spec says "fat JAR".

### 10.3. For CLI Tools, Maven Plugins, and Specialized Java Libraries

If the app is a pure Java CLI tool using `main` with no Spring Boot app lifecycle, Shade/Shadow is often well-suited to release **a single directly runnable JAR**. If the goal is a **library for others to embed**, `shadedArtifactAttached` (Maven) or a suitable variant (Gradle) helps publish a **relocated build** without overwriting the thin artifact. Still ensure Maven POM/Gradle module metadata accurately reflects dependencies and avoids bringing duplicate classes into consumers.

**A Boot executable JAR is unsuitable for direct use as a library dependency** because app classes reside under `BOOT-INF/classes`; a consuming project's compiler/classloader does not treat that as a normal layout. Extract shared classes into a library module producing a thin JAR or publish an appropriate artifact per Boot docs.

## 11. How to Verify JAR Types in CI

### 11.1. Step 1: Run jar tf

~~~bash
jar tf target/nested-boot-0.0.1-SNAPSHOT.jar
jar tf target/flat-maven-1.0.0-all.jar
jar tf build/libs/flat-gradle-1.0.0-all.jar
~~~

These paths belong to **the three separate projects** in this lesson; run each in its respective project root, not all three in one folder unless artifacts were copied to a shared spot.

Identification table:

| What you see | Appropriate conclusion |
| --- | --- |
| `BOOT-INF/classes` + `BOOT-INF/lib/*.jar` + Boot `JarLauncher` | Standard Boot nested executable JAR |
| `org/apache/commons/lang3/StringUtils.class` directly at root and `Main-Class=App` | Shaded/uber JAR from the example |
| Only `com/example/archives/App.class`, no Commons Lang classes/JAR | Thin JAR, requires external runtime classpath |
| `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | Boot executable WAR layout (different from JAR) |
| No `BOOT-INF/lib` yet `BOOT-INF/classes` present | May be a custom archive or missing dependencies; check manifest and build log |

`jar tf` only lists **entries of the current JAR** without extracting files inside nested JAR entries. To inspect a specific class inside a Boot nested archive's dependency, know that it lives in `BOOT-INF/lib/<dependency>.jar` and inspect that dependency with a ZIP tool, while **never repacking the production artifact** during diagnosis.

### 11.2. Step 2: Read Main-Class and Start-Class

If the environment has `unzip`:

~~~bash
unzip -p target/nested-boot-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
unzip -p target/flat-maven-1.0.0-all.jar META-INF/MANIFEST.MF
~~~

Expected patterns:

~~~text
Boot:   Main-Class=org.springframework.boot.loader.launch.JarLauncher
        Start-Class=com.example.archives.NestedBootApplication

Shade:  Main-Class=com.example.archives.App
        (Start-Class not needed by Boot Loader)
~~~

The `Boot:` and `Shade:` lines are **illustrative summary notes**, not the literal manifest format. In a real manifest file, each attribute uses `Name: Value` format.

### 11.3. Step 3: Run the Exact Artifact to Be Released

~~~bash
java -jar target/nested-boot-0.0.1-SNAPSHOT.jar
java -jar target/flat-maven-1.0.0-all.jar
java -jar build/libs/flat-gradle-1.0.0-all.jar
~~~

Expected:

~~~text
BOOT_OK Hello
FLAT_OK Hello
FLAT_OK Hello
~~~

These are **three results from three independent runs**, not one command printing three consecutive lines. Boot prints startup logs in addition to the app line; the flat CLI examples only print the single line from `main` on success. With logging/agents or unusual environments, stdout may include extra lines.

### 11.4. Step 4: Compare Dependency Tree and Archive

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

The dependency tree shows **which versions** Maven/Gradle selected; `jar tf` shows **which files are actually inside the artifact**. When Shade/Shadow merges, `.class` files lose source JAR name metadata in the layout; do not rely on an uber JAR's `jar tf` to guess original dependency versions.

### 11.5. Step 5: Check for Resource/Service Errors

Beyond running `main`, verify features requiring SPI/reflection/auto-configuration:

- `ServiceLoader` finds all required providers.
- Spring context initializes and creates all beans (when using Boot).
- Serialization, JSON modules, JDBC drivers, and logging providers work properly.
- Resource lookups find the right `META-INF/*`.
- No unexpected duplicate entries or `SecurityException` from signature files.
- Artifact name/classifier matches the release pipeline.

Merely having `java -jar` run and print "Hello" is not enough to declare a Spring Boot app with dozens of starters safely shaded.

## 12. Speed, Size, Layering, and Supply Chain

### 12.1. Startup Speed

There is no universal conclusion that "nested JAR is slower" or "shaded JAR is faster". Startup is affected by classloading, file I/O, filesystem/cache, CPU, JIT, reflection, Spring bean creation, container base image, and dependency count.

- Nested JAR: Boot Loader incurs loader/classpath initialization overhead, while keeping libraries packaged in an optimized Boot layout supporting multiple packaging models.
- Shaded JAR: nominally fewer classpath entries, yet massive merges or botched metadata handling can also slow or break startup; package relocation and minimization carry their own effects.

To compare, build **identical functionality**, use the same JDK/runtime, repeat benchmarks multiple times after warmup, and measure from process start to real readiness. Do not compare different file sizes and infer startup time.

### 12.2. Docker/OCI Layers

A Spring Boot nested executable JAR can include `BOOT-INF/layers.idx`. Boot Maven/Gradle tooling or container-image tooling can use this metadata to split dependencies, loader, snapshot dependencies, and app classes into separate layers; this can improve cache reuse when only application code changes.

A shaded JAR does not automatically have Boot `layers.idx`, because classes/resources are merged into one archive. Multi-layer images can still be built using other strategies, though with custom configuration and tooling; **do not claim shaded JARs cannot be containerized**.

### 12.3. File Size and Reproducibility

- Nested JAR keeps individual dependency archives (some already compressed). The `STORED` outer entry is required for Boot Loader seeking, so do not estimate size by "double compression".
- Shade/Shadow merges bytes and can handle duplicate resources and relocation/minimization. Larger/smaller size depends on contents and configuration.
- Reproducible builds depend on version locks/BOMs, timestamps, file ordering, archive settings, and build environments. You can verify checksums across **identical build inputs** on stable CI.
- When a library has a license/NOTICE requiring distribution attribution, shading does not waive keeping them. Never strip `META-INF/LICENSE`/`NOTICE` just for size optimization if doing so violates license terms.

### 12.4. Dependency Scanning and SBOM

In a Boot nested JAR, each nested dependency usually retains a clear filename/version, helping many JAR analyzers identify boundaries. In a shaded JAR, class files are merged and packages may be relocated; a scanner inspecting only the archive may struggle to deduce exact library origins.

**Neither packaging format guarantees security by itself:** you must still pin dependencies, scan vulnerabilities via the build-time dependency graph, store SBOMs (SPDX/CycloneDX if policy requires), verify licenses, and release only tested artifacts.

## 13. Common Errors and Remedies

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Boot JAR has `BOOT-INF/lib`, yet `java -cp app.jar Main` reports missing class | Standard JVM does not understand nested JAR classpath | Run `java -jar`, use Boot Loader manifest; do not treat outer jar as thin classpath |
| `no main manifest attribute` when running JAR | Running thin JAR, or Shade/Shadow did not set Main-Class | Check `META-INF/MANIFEST.MF` and actual artifact/classifier |
| Boot executable JAR manifest `Main-Class` is app main | Another plugin/transformer overwrote manifest or wrong layout | Re-establish build ownership, use standard Boot `repackage` plugin |
| Shaded JAR throws `NoClassDefFoundError` | Dependency excluded, minimized away, or classpath/version conflict | Check dependency tree, include/minimize rules, `jar tf` |
| Shade/Shadow has classes yet Spring beans/auto-config missing | Spring META-INF resources overwritten without merge | Check auto-config imports/factories, prefer default Boot nested when appropriate |
| `ServiceLoader` sees only one provider | Colliding `META-INF/services` dropped | Use ServicesResourceTransformer/mergeServiceFiles with right duplicate strategy |
| Shadow `mergeServiceFiles()` has no effect | `duplicatesStrategy=EXCLUDE` dropped inputs before transformer | Enable INCLUDE for service descriptors, handle other resources explicitly |
| `SecurityException: Invalid signature file digest` | Merged JAR retained signature files from dependencies whose bytes changed | Strip invalidated signatures from merged artifact; keep build-time provenance verification |
| `FileNotFoundException` when library looks for real JAR path | Library assumes dependency is an external file on disk | Check classloader/resource APIs, `requiresUnpack` if library truly needs it |
| Two plugins packaging together yield unpredictable output | Shade and Boot repackage writing same artifact/manifest | Separate artifacts/classifiers/tasks, smoke-test exact release file |
| `jar tf` cannot find `StringUtils.class` in Boot JAR | Class sits inside nested commons-lang3 JAR | Look for `BOOT-INF/lib/commons-lang3-...jar` instead of root class |
| Gradle reports Shadow plugin incompatibility | Shadow 9.3.0 requires Gradle >= 9.0, Java >= 17 | Use compatible Gradle Wrapper/plugin release |
| JAR shrank yet runtime fails on reflection | `minimize` stripped dynamically loaded classes | Disable minimize/define exclusions, run full integration tests |
| Maven build has two JARs `...jar` and `...-all.jar` | `shadedArtifactAttached=true` | Publish right classifier; do not deploy thin JAR by mistake |
| Runtime version differs from dependency tree | Stale artifact or plugin filter/relocation differs from current build | `clean package`, check build logs, checksums, and output artifact |

### 13.1. Three-Question Diagnostic Method

**Question A — What type of archive is it?** Run `jar tf` looking for `BOOT-INF/lib` (nested) or root dependency classes (shaded).

**Question B — What is the entry point?** Read the manifest. Boot `JAR` layout has `Main-Class: JarLauncher` + `Start-Class`; shaded CLI has `Main-Class` set to the app.

**Question C — Are required resources intact?** For Shade/Shadow, check `META-INF/services`, Spring metadata, duplicates, relocation, and class loaders. For Boot nested, verify dependencies are in `BOOT-INF/lib` and not excluded by the build plugin.

## 14. Practice Exercises

**Exercise 1 — File identification.** One JAR has `BOOT-INF/classes` and `BOOT-INF/lib/foo-1.0.jar`. Another JAR has `org/example/Foo.class` at the root. Which JAR is nested?  
**Answer:** The first JAR uses Boot's nested layout; the second shows signs of flattened/merged classes (or could be a thin JAR) and needs manifest/dependency inspection to classify accurately.

**Exercise 2 — Manifest.** Why doesn't a Boot JAR `Main-Class` normally point directly to `@SpringBootApplication`?  
**Answer:** Because Boot Loader must initialize a classloader accessing `BOOT-INF/classes` and nested dependencies before invoking the application's `Start-Class`.

**Exercise 3 — Stdout result.** Run the three examples in the lesson. Boot prints `BOOT_OK Hello`, while Shade and Shadow print `FLAT_OK Hello`. Does differing packaging inherently change business logic output?  
**Answer:** No. The main differences are layout and classloading. These examples print different prefixes to tell the projects apart, not because nested/shaded alters logic.

**Exercise 4 — Java SPI.** Two JARs contain the same `META-INF/services/com.example.spi.Plugin` path, each declaring a different implementation. What happens if Shade keeps only the first file?  
**Answer:** The second file's provider can be lost; use ServicesResourceTransformer. Shadow needs `mergeServiceFiles` and proper duplicate handling.

**Exercise 5 — Jar tf.** Why can't you just run `jar tf boot-app.jar` and search for `org/apache/commons/lang3/StringUtils.class`?  
**Answer:** `jar tf` only lists outer JAR entries, while the class resides inside `BOOT-INF/lib/commons-lang3-3.17.0.jar`.

**Exercise 6 — Relocation.** A project is a library embedded into other apps that have dependency version conflicts. Which feature helps more: Boot repackage or Shade/Shadow relocation?  
**Answer:** Tested Shade/Shadow relocation can help since namespace renaming is needed; a Boot executable JAR is not a standard library dependency format.

**Exercise 7 — Building both formats side by side.** You need a Boot runnable JAR and a thin library JAR for other modules. Should one single archive serve as both?  
**Answer:** No. Use separate artifacts/modules/classifiers with explicit outputs and publishing; a library should have a normal root class layout.

**Exercise 8 — Choosing packaging.** A Spring Boot REST API uses many starters, Jackson modules, and Spring auto-config. A team plans to Shade everything "to shrink container image size". What should be done first?  
**Answer:** Prefer the Boot plugin/nested JAR and Boot layers/tooling; measure actual image size/startup. If Shading is still desired, design metadata merging and integration tests rather than citing the term "fat JAR" as justification.

## 15. Pre-Release Checklist

- [ ] Identified whether the artifact is a Spring Boot nested JAR, shaded/uber JAR, or thin JAR.
- [ ] Read `META-INF/MANIFEST.MF` and verified `Main-Class`/`Start-Class` match the layout.
- [ ] For Boot: confirmed `BOOT-INF/classes`, `BOOT-INF/lib`, Boot Loader, and successful `java -jar` run.
- [ ] For Shade/Shadow: confirmed required dependencies in root classes/resources and manifest pointing to app main.
- [ ] Checked dependency tree/versions against the final artifact **actually being deployed**.
- [ ] Evaluated resource collisions, `META-INF/services`, and Spring metadata when merging.
- [ ] Relocation/minimization enabled only with a clear use case and integration tests covering reflection/SPI.
- [ ] Handled signatures/NOTICE/licenses and reviewed compliance requirements.
- [ ] Ensured Boot repackage and Shade/Shadow do not accidentally target the same output or classifier.
- [ ] If using Shadow, verified plugin ID/version matches actual Gradle/Java versions.
- [ ] Have a smoke test running the file via `java -jar` in a production-like environment.
- [ ] Saved build provenance, dependency graph, and SBOM per team requirements.

## 16. Official Documentation

- Spring Boot 3.5 — Nested JARs: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html
- Spring Boot 3.5 — Launching Executable Jars: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html
- Spring Boot 3.5 — Executable Jar Restrictions: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Build/Using a Boot App as Dependency: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Maven Shade Plugin — Executable JAR: https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html
- Maven Shade Plugin — Resource Transformers: https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html
- Maven Shade Plugin — Class Relocation: https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html
- GradleUp Shadow — Getting Started: https://gradleup.com/shadow/getting-started/
- GradleUp Shadow — Merging and Duplicates: https://gradleup.com/shadow/configuration/merging/
- GradleUp Shadow — Relocation: https://gradleup.com/shadow/configuration/relocation/
- GradleUp Shadow — Compatibility Matrix: https://gradleup.com/shadow/
- Commons Lang 3.17.0 Artifact: https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0

**Conclusion:** For Spring Boot applications, **nested executable archive + Boot Loader** is the standard packaging path: dependencies stay as separate JARs in `BOOT-INF/lib` and the loader knows how to load them. Maven Shade/Gradle Shadow create **JARs merging classes/resources**, useful for Java CLIs or library relocation, yet require proactively handling resource collisions, SPI, manifests, and metadata. Never equate "just one JAR file" with "the same classloading mechanism"; use `jar tf`, manifests, and smoke tests to verify the artifact you deploy.
