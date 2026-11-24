# Role of classpath.idx and Library Loading Order in Spring Boot Loader

## 1. Lesson Objectives

A Spring Boot application may run normally in an IDE or via `mvn spring-boot:run` / `gradle bootRun`, yet fail after being packaged and run with `java -jar`. One cause worth checking is that the **development classpath** is not necessarily identical to the **classpath built by Spring Boot Loader from nested JAR libraries**.

In a Spring Boot executable JAR, the key components typically reside in:

- `BOOT-INF/classes/`: the **application's** classes and resources.
- `BOOT-INF/lib/`: **dependency JARs** packaged for runtime use.
- `META-INF/MANIFEST.MF`: specifies the launcher and the application's main class.
- `org/springframework/boot/loader/...`: Spring Boot Loader classes.
- `BOOT-INF/classpath.idx` (if present): index of **the order in which nested JARs are added to the classpath**.
- `BOOT-INF/layers.idx` (if present): **archive layering info for Docker/OCI**, not library loading order.

**Key point:** `classpath.idx` is not a dependency declaration, not a BOM or version-defining file, and not a log of which classes **were actually loaded by the JVM**. It describes the **search-location order** when Boot Loader prepares the classpath for an executable archive.

### Distinction Table Before Hands-On Practice

| Question | Where to read? | Avoid false conclusions |
|---|---|---|
| Which libraries and versions were chosen by Maven/Gradle? | `dependency:tree` or `runtimeClasspath` | Do not infer solely from `classpath.idx` |
| Which JARs were actually packaged into the artifact? | `jar tf app.jar` looking at `BOOT-INF/lib/` | Do not infer solely from `pom.xml` |
| In what order are nested libraries added to the classpath? | `BOOT-INF/classpath.idx` | Do not substitute line order from `jar tf` |
| Which JAR did a specific class come from? | `CodeSource`, classloader, `-Xlog:class+load` | Do not assert with certainty solely from the index |
| When is a class loaded by the JVM? | On demand by the JVM and actual classloader | Not "every JAR listed earlier is loaded first" |
| Which Docker layer is a library in? | `BOOT-INF/layers.idx` | Layer order differs from classpath order |

## 2. Why Does Spring Boot Need a Loader for Nested JARs?

The standard Java launcher can run `java -jar app.jar` if the JAR's manifest has an appropriate entry point. However, the Java launcher **does not automatically turn every JAR inside a JAR into a classpath entry**. Spring Boot provides a loader to solve this, enabling distribution of a single executable JAR that preserves nested libraries instead of unpacking all classes into a shaded JAR.

Diagram of an **illustrative** executable JAR:

```text
index-lab-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/
│   └── springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/indexlab/IndexLabApplication.class
    ├── lib/
    │   ├── spring-boot-3.5.16.jar
    │   ├── commons-lang3-3.17.0.jar
    │   └── ... (many other JARs)
    ├── classpath.idx
    └── layers.idx
```

Filenames and additional component locations in an **actual archive** depend on plugins, versions, dependency resolution, and configuration. Do not use the diagram as proof that a specific build contains these exact entries.

In Spring Boot 3.x, `META-INF/MANIFEST.MF` usually contains:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.indexlab.IndexLabApplication
```

`Main-Class` points only to bootstrapping **JarLauncher**. `Start-Class` points to the application entry point. Spring Boot Loader sets up the appropriate classpath, then invokes the application's `main` method.

Commonly encountered launchers:

- **`JarLauncher`**: uses `BOOT-INF/classes/` and JARs in `BOOT-INF/lib/`.
- **`WarLauncher`**: for executable WARs, with `WEB-INF/classes/`, `WEB-INF/lib/`, and `WEB-INF/lib-provided/` depending on packaging.
- **`PropertiesLauncher`**: allows configuring additional paths such as `loader.path` per its own features.

**Do not mechanically apply JarLauncher behavior to every layout/launcher.** If inspecting a WAR, a custom launcher, or an extracted-layer image, first verify the manifest and how the application is actually started.

### Plain JAR vs. Executable JAR

| Plain Java JAR | Spring Boot executable JAR |
|---|---|
| Module classes usually at package root, e.g., `com/example/App.class` | Application classes in `BOOT-INF/classes/com/example/App.class` |
| Does not bundle all runtime dependencies | Usually bundles nested JARs in `BOOT-INF/lib/` |
| Typically used as a library/normal classpath entry | Designed to be launched by Spring Boot Loader via `java -jar` |
| Does not necessarily have a classpath index | May have `BOOT-INF/classpath.idx` |

If Gradle produces both `myapp-plain.jar` and `myapp.jar`, make sure to inspect the **Boot executable artifact**. In Maven, `spring-boot-maven-plugin:repackage` normally replaces the plain JAR with the executable one when configured accordingly.

## 3. What Is classpath.idx? Standard Format

`classpath.idx` is an **ordered list of nested JAR paths**. The file is placed at `BOOT-INF/classpath.idx` inside an executable archive compatible with Spring Boot Loader. Per Spring Boot documentation, both executable JARs and executable WARs can provide a classpath index.

Example archive with two libraries:

```text
BOOT-INF/lib/dependency-a.jar
BOOT-INF/lib/dependency-b.jar
```

The index **may** list:

```text
- "BOOT-INF/lib/dependency-b.jar"
- "BOOT-INF/lib/dependency-a.jar"
```

That states that when the file is used by the loader, `dependency-b.jar` is added to the classpath **before** `dependency-a.jar`. This is an independent example; it does **not** mean the order is always reverse-alphabetical.

### Rules for Writing an Entry

1. Lines begin with a **hyphen followed by a space**: `- `.
2. The nested JAR path is enclosed in **double quotes**.
3. The name is the **entry path inside the archive**, e.g., `BOOT-INF/lib/example-1.0.jar`, not `C:\libs\example.jar` or `group:artifact:version`.
4. Line order is the order in which JARs should be added to the classpath.
5. The syntax is only **YAML-compatible**: Spring Boot **does not use a general-purpose YAML parser** to read the index. Do not arbitrarily omit quotes, substitute YAML objects or JSON, or add other structures.

Examples of **non-standard** lines:

```text
BOOT-INF/lib/alpha.jar
- BOOT-INF/lib/beta.jar
- "org.example:gamma:1.0"
```

In the invalid examples: line 1 lacks `- "..."`; line 2 lacks quotes; line 3 uses Maven coordinates rather than a nested archive path.

**The index is usually generated automatically by the Spring Boot Maven/Gradle build plugin.** When dependency versions change, the file in the archive must reflect the new JAR names. Therefore, do not manually maintain a static index outside the build process and "stuff it back" into the final executable JAR.

### The Index Does Not Replace the Dependency Resolver

Things `classpath.idx` **does not do**:

- Does not download libraries from Maven Central or other repositories.
- Does not add missing JARs to `BOOT-INF/lib`.
- Does not choose between two dependency versions when Maven/Gradle resolves the graph.
- Does not automatically remove redundant libraries.
- Does not replace `runtime`/`provided` scopes or Gradle configurations.
- Does not turn an executable JAR into a regular library JAR.
- Does not guarantee classes in an earlier JAR will be initialized earlier by the JVM.

## 4. When Does Boot Loader Read the Index?

**The most important scope limit** from Spring Boot documentation: the classpath index is only used when **the executable archive is run via `java -jar`**. It is not used when running directly in an IDE or with standard development-run commands.

| Launch method | Does Boot Loader use the archive's `classpath.idx`? | Explanation |
|---|---|---|
| `java -jar target/app.jar` | Yes, if archive/index is valid and launcher supports it | Runs through executable archive and Boot Loader |
| `java -jar build/libs/app.jar` | Yes, with properly packaged `bootJar` artifact | Same as above |
| `./mvnw spring-boot:run` | **No** | Maven plugin sets up development classpath |
| `./gradlew bootRun` | **No** | Gradle task uses main source set and runtime classpath |
| Running main class in IDE | **No** | IDE determines the project classpath |
| `java -cp ... com.example.App` | **Does not automatically read index** | Standard launcher per `-cp`, does not automatically open Boot archive nested libraries |
| WAR deployed to a traditional servlet container | **Does not use Boot `java -jar` mechanism** | Container has its own classloader policy |

Hence "works in IDE but fails under `java -jar`" **may** relate to the classpath index, or could be due to a missing runtime dependency, unpackaged resource, profile config, different JDK version, file path, or container classloader.

### Why Is java -cp app.jar Not Equivalent to java -jar app.jar?

In an executable JAR, application classes sit under `BOOT-INF/classes` and libraries under `BOOT-INF/lib`. The standard Java launcher with:

```bash
java -cp target/app.jar com.example.App
```

does not automatically treat `BOOT-INF/classes` and every nested JAR as classpath entries. The normal way to launch an executable Boot archive is:

```bash
java -jar target/app.jar
```

Inspecting the archive's `classpath.idx` alone is meaningless if the application actually runs via `bootRun`, an IDE, or a custom mechanism that does not use that index.

## 5. Classpath Order and Class Loading Order Are Not the Same

Consider two libraries:

```text
a-lib.jar  -> contains com/example/Feature.class
b-lib.jar  -> also contains com/example/Feature.class
```

If the same class name appears on the same **linear classpath**, the JAR searched first typically supplies the class definition. That is where nested JAR order can matter.

However, **classpath order is search order, not the chronological order in which each class is loaded**:

- The JVM may load classes only when they are actually used.
- A ClassLoader typically **delegates** to its parent loader per its rules; classes from the JDK or parent loader are not simply overridden by the position of a nested JAR.
- A class already defined by a loader does not change its source if the search path changes afterward.
- Different classloaders can define a same-named class as two distinct types.
- Java module path, agents, ServiceLoader, container classloaders, or devtools restart loaders can alter behavior compared to a flat classpath.

An accurate statement:

> "`classpath.idx` determines the order in which **nested JARs are added to the classpath** for Boot Loader to search for classes/resources."

An **incorrect** statement:

> "The JVM will load every class in the JAR on line one, and only then move to the JAR on line two."

### Impact on Resources and SPI

Multiple JARs may contain the same resource `config/default.properties`, the same `META-INF/MANIFEST.MF`, or multiple `META-INF/services/<interface>` descriptors. When calling `ClassLoader.getResource` or `getResources`, search-path order **can** affect which location is returned. `ServiceLoader` has its own provider-loading rules; classpath order can affect it, but **does not** replace `META-INF/services` metadata.

A resource file not being found when running a packaged JAR can stem from:
- Resource not packaged into `BOOT-INF/classes` or a dependency JAR.
- Another JAR having a same-named resource found earlier.
- An API using a different context classloader than the one you are inspecting.
- Wrong case in the resource path or confusing filesystem loading with classpath loading.

## 6. Runnable Example on Java 17: Swapping the Order of Two JARs Containing the Same Class

This is a **pure Java model**, not a Spring Boot application, to observe the effect of **class search order** in an independently verifiable way.

Create the files:

```text
classpath-order-lab/
├── src/alpha/lib/Marker.java
├── src/beta/lib/Marker.java
└── src/app/lab/app/OrderProbe.java
```

Contents of `src/alpha/lib/Marker.java`:

```java
package lib;

public final class Marker {
    private Marker() {}

    public static String origin() {
        return "alpha";
    }
}
```

Contents of `src/beta/lib/Marker.java`:

```java
package lib;

public final class Marker {
    private Marker() {}

    public static String origin() {
        return "beta";
    }
}
```

These two files **intentionally define the same `lib.Marker` name** for this experiment. **Do not** leave this kind of conflict in a production application.

Contents of `src/app/lab/app/OrderProbe.java`:

```java
package lab.app;

import lib.Marker;

public final class OrderProbe {
    public static void main(String[] args) {
        System.out.println(Marker.origin());
    }
}
```

On Linux/macOS, from the example root using JDK 17+:

```bash
mkdir -p out/alpha out/beta out/app

javac -d out/alpha src/alpha/lib/Marker.java
javac -d out/beta src/beta/lib/Marker.java

jar --create --file out/alpha.jar -C out/alpha .
jar --create --file out/beta.jar -C out/beta .

javac -cp out/alpha.jar -d out/app src/app/lab/app/OrderProbe.java

# alpha.jar before beta.jar:
java -cp "out/app:out/alpha.jar:out/beta.jar" lab.app.OrderProbe

# beta.jar before alpha.jar:
java -cp "out/app:out/beta.jar:out/alpha.jar" lab.app.OrderProbe
```

**Exact stdout** of the first `java` command:

```text
alpha
```

**Exact stdout** of the second `java` command:

```text
beta
```

Class `OrderProbe` was compiled **once**, while the runtime classpath changed. Both versions of `lib.Marker` have the same method signature, so no linkage error occurs; the returned value proves different JARs were selected.

Windows PowerShell uses a semicolon in the classpath:

```powershell
New-Item -ItemType Directory -Force out/alpha, out/beta, out/app | Out-Null
javac -d out/alpha src/alpha/lib/Marker.java
javac -d out/beta src/beta/lib/Marker.java
jar --create --file out/alpha.jar -C out/alpha .
jar --create --file out/beta.jar -C out/beta .
javac -cp out/alpha.jar -d out/app src/app/lab/app/OrderProbe.java

java -cp "out/app;out/alpha.jar;out/beta.jar" lab.app.OrderProbe
java -cp "out/app;out/beta.jar;out/alpha.jar" lab.app.OrderProbe
```

The last two commands print `alpha` and `beta` respectively. **Lesson applied to Boot:** if two nested JARs accidentally contain the same class/resource name, the order established by Boot Loader can change which source is picked. However, a JDK `-cp` experiment **does not prove** the exact behavior of a Boot archive; you must inspect the actual `classpath.idx` and runtime classloader in that artifact.

## 7. Complete Spring Boot Maven Example: Creating an Executable Archive and Reading the Index

The example pins Spring Boot **3.5.16** and Java **17+** for version-reproducible results. Do not assume this is the latest release at all times. Requires Maven 3.6.3+ or the project's Maven Wrapper, JDK, and repository access if the cache is incomplete.

Structure:

```text
index-lab/
├── pom.xml
└── src/main/java/com/example/indexlab/IndexLabApplication.java
```

### 7.1. pom.xml

```xml
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
    <artifactId>index-lab</artifactId>
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
```

`spring-boot-starter-parent` manages dependencies/plugins and configures `repackage` in the lifecycle. `spring-boot-starter` actually adds the Spring dependencies; a BOM/parent **does not automatically add** them unless declared. `commons-lang3` is chosen with an explicit version to provide an easily recognizable nested JAR.

### 7.2. Complete Java Class

`src/main/java/com/example/indexlab/IndexLabApplication.java`:

```java
package com.example.indexlab;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IndexLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IndexLabApplication.class, args);
    }

    @Bean
    CommandLineRunner probe() {
        return args -> {
            System.out.println("Loader demo ready");
            System.out.println("Capitalize = " + StringUtils.capitalize("spring"));
        };
    }
}
```

The app uses `spring-boot-starter` (no web starter), so it runs in the console and exits after the relevant components finish. Run at the example root, using **one** of the two build styles:

```bash
# Only if the project already has Maven Wrapper:
./mvnw clean package

# If there is no wrapper, use installed Maven:
mvn clean package

# Run the repackaged archive:
java -jar target/index-lab-0.0.1-SNAPSHOT.jar
```

The exact two lines **printed by the application**:

```text
Loader demo ready
Capitalize = Spring
```

Other Spring Boot, Maven, or JVM logs may appear; do not claim the entire stdout consists of only these two lines. Windows PowerShell uses `.\mvnw.cmd clean package` if a wrapper is present, or `mvn clean package`.

### 7.3. List the Archive and Read the Index with JDK Tools

Linux/macOS:

```bash
# Inspect BOOT-INF and actual libraries:
jar tf target/index-lab-0.0.1-SNAPSHOT.jar
jar tf target/index-lab-0.0.1-SNAPSHOT.jar | grep -E '^(BOOT-INF/classpath.idx|BOOT-INF/lib/)'

# Extract only the index file to a temp dir without modifying the archive:
mkdir -p inspect
cd inspect
jar xf ../target/index-lab-0.0.1-SNAPSHOT.jar BOOT-INF/classpath.idx
cat BOOT-INF/classpath.idx
cd ..
```

PowerShell:

```powershell
jar tf target/index-lab-0.0.1-SNAPSHOT.jar | Select-String 'BOOT-INF/(classpath\.idx|lib/)'

New-Item -ItemType Directory -Force inspect | Out-Null
Push-Location inspect
jar xf ../target/index-lab-0.0.1-SNAPSHOT.jar BOOT-INF/classpath.idx
Get-Content BOOT-INF/classpath.idx
Pop-Location
```

`jar` comes with the JDK; `jar xf <archive> <entry>` **extracts the file** into the current working directory without modifying the original artifact. When an archive lacks an index file, `Get-Content`/`cat` will not find the file; in that case inspect the artifact type, plugin, and manifest rather than guessing the contents.

Items to cross-check:

1. Is `BOOT-INF/classes/com/example/indexlab/IndexLabApplication.class` present?
2. Is `BOOT-INF/lib/commons-lang3-3.17.0.jar` present?
3. Is `BOOT-INF/classpath.idx` present? If so, do lines list library names in `- "BOOT-INF/lib/...jar"` format?
4. Which transitive dependencies were brought in by Spring Boot starter?
5. Does `META-INF/MANIFEST.MF` have the appropriate `Main-Class` and `Start-Class`?
6. Under `java -jar`, does the application actually run and print the two expected lines?

**Do not assert the exact order of all libraries in the example before running the build.** Order depends on resolution, how the plugin generates the index, and reproducible build settings. For a specific artifact, the extracted index content is the most accurate evidence.

### 7.4. Read the Dependency Graph in Parallel

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
```

Use `mvn` instead of `./mvnw` when there is no wrapper. `dependency:tree` tells you **which libraries were chosen and how they entered**; `jar tf` tells you **which libraries are in the executable archive**; `classpath.idx` tells you **nested JAR order on the classpath**. No single command can replace all three checks.

## 8. Gradle: Comparing bootRun vs. bootJar

If using Gradle instead of Maven, use **the same `IndexLabApplication.java` class** above with the following two Groovy DSL files.

`settings.gradle`:

```groovy
rootProject.name = 'index-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Gradle `platform(...)` uses the BOM for dependency constraints; the Spring Boot plugin works with the Java plugin to provide `bootJar`/`bootRun`. When the project **already has a Gradle Wrapper**:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Does not use classpath.idx:
./gradlew bootRun

# Creates executable archive:
./gradlew clean bootJar
jar tf build/libs/index-lab-0.0.1-SNAPSHOT.jar

# Can use the index packaged in the archive:
java -jar build/libs/index-lab-0.0.1-SNAPSHOT.jar
```

Windows uses `.\gradlew.bat` instead of `./gradlew`. If no wrapper exists yet, generate one using an installed Gradle version compatible with Spring Boot 3.5; `gradlew` does not appear merely by writing a build script.

To read the classpath index of the Gradle artifact, replace `target/index-lab-...jar` in Section 7.3 with `build/libs/index-lab-...jar`. Do not assume the line order in `build.gradle` or `dependencies` output will **always** match `classpath.idx`; especially if the build is configured for reproducibility.

### Maven and Gradle: Three Corresponding Observation Steps

| Goal | Maven | Gradle |
|---|---|---|
| Dev run, without archive index | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Inspect resolved dependencies | `dependency:tree` | `dependencies --configuration runtimeClasspath` |
| Build executable archive | `./mvnw package` (repackage configured) | `./gradlew bootJar` |
| Inspect archive | `jar tf target/*.jar` (pick right file) | `jar tf build/libs/*.jar` (pick right file) |
| Run via Boot Loader | `java -jar target/actual.jar` | `java -jar build/libs/actual.jar` |

In multi-module projects, Gradle `:service-app:bootJar` or Maven `-pl :service-app` only works when the module actually exists. Another root `build/libs` does not mean tests in a submodule produced an executable JAR for that module.

## 9. Reproducible Builds: Why Might Order Be Alphabetical?

Spring Boot documentation confirms two important behaviors:

1. The index generated by Maven/Gradle plugins usually reflects the classpath the build tool uses to run/test.
2. **When reproducible builds are enabled**, entries in `classpath.idx` are **sorted alphabetically**.

Consequence: **do not** treat dependency declaration order in a build script as a fixed contract for runtime JAR order across every build. Also do not confuse **ZIP entry order** (`jar tf` command) with **classpath order** (the index file).

Illustrative alphabetically sorted index:

```text
- "BOOT-INF/lib/alpha-1.0.jar"
- "BOOT-INF/lib/beta-2.0.jar"
- "BOOT-INF/lib/omega-1.0.jar"
```

This is an example file, **not guaranteed contents** of any given app. Even when sorted alphabetically, it still only governs the **search** order for classes/resources when needed, not "load all of alpha then beta then omega".

If a project only works when `old-api.jar` precedes `new-api.jar`, that indicates a conflicting and fragile configuration. The sustainable fix is managing versions and excluding unneeded transitive dependencies, rather than relying on incidental archive order.

## 10. Confirming Where a Class Was Actually Loaded From

When suspecting a class was picked up from an unwanted JAR, you can print **CodeSource**. The following is code inserted **inside a Java method**, not a standalone file:

```java
Class<?> type = org.apache.commons.lang3.StringUtils.class;
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "Unknown source"
        : source.getLocation());
```

The output may be a URL describing a nested JAR, a local path, or no code source, depending on the JVM and classloader; **do not** assume a fixed stdout before running.

With JDK 17, enable class loading logging:

```bash
java -Xlog:class+load=info -jar target/index-lab-0.0.1-SNAPSHOT.jar
```

Note that `-Xlog:class+load=info` must appear **before `-jar`** because it is a JVM option; this command can print many lines. Filter the log for a specific class, such as `org.apache.commons.lang3.StringUtils`, instead of trying to read everything.

If suspecting **duplicate resource names**, inside a Java method you can use:

```java
var loader = Thread.currentThread().getContextClassLoader();
var urls = loader.getResources("META-INF/MANIFEST.MF");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

This snippet can throw `IOException` from `getResources`; the enclosing method must declare or handle the checked exception. `getResources` can return multiple URLs, while `getResource` returns one resource per the loader's rules. Do not mistake them for ordinary filesystem files.

### When Other Classloaders Are Involved

Spring Boot Devtools, application servers, test runners, IDE agents, or plugins can create **multiple classloaders**. Two classes with the same name under different classloaders may be treated as **two different types**, leading to `ClassCastException`. In that case, print `SomeClass.class.getClassLoader()`, the code source, and the classloader of the related object, rather than only looking at the index. Parent delegation can also cause a class to be found from the parent before nested JARs.

## 11. Distinguishing classpath.idx and layers.idx

Two similarly named files that sometimes both reside in `BOOT-INF/`:

| Aspect | `classpath.idx` | `layers.idx` |
|---|---|---|
| Purpose | Order in which nested JARs are added to classpath | Splits archive components into Docker/OCI layers |
| Data | List of JAR paths | Layer names and files/directories belonging to each layer |
| When meaningfully active | When Boot Loader launches via `java -jar` | When build/extract/container image tools process layers |
| Format | Each line `- "BOOT-INF/lib/x.jar"` | Layer name followed by indented sub-paths |
| What it does not do | Does not pick versions / does not add JARs | Does not control JVM class lookup order |

Illustrative `layers.idx` example:

```yaml
- "dependencies":
  - "BOOT-INF/lib/dependency-a.jar"
  - "BOOT-INF/lib/dependency-b.jar"
- "application":
  - "BOOT-INF/classes/"
  - "META-INF/"
```

This content structure serves layer extraction/OCI caching. **Changing layer order is not a way to adjust classpath order.** Docker layer order and Java classpath search order are two independent concerns.

## 12. Common Errors and Remedies

| Symptom | Hypothesis to verify | Appropriate action |
|---|---|---|
| Cannot find `BOOT-INF/classpath.idx` | Opening a plain JAR, or plugin/layout did not generate index | Check manifest, `BOOT-INF/lib`, `repackage`/`bootJar` plugin; index is optional |
| File exists but missing expected JAR name | Dependency not packaged, excluded, or wrong scope | Compare index against `jar tf` and resolved dependency tree |
| IDE/`bootRun` works, `java -jar` fails | Development classpath differs from runtime archive | Check packaging, code source, index, runtime profiles |
| `ClassNotFoundException` | Class missing from runtime classpath | Locate right dependency, scope/config, and packaged JAR |
| `NoClassDefFoundError` | Missing class or initialization/linkage error | Read `Caused by`, check source JAR and initialization |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary conflict between compile/run versions | Identify actually loaded JAR, fix dependency graph |
| Resource picked from wrong JAR | Two JARs contain identically named resource | `getResources`, investigate classloader and resource path |
| `ServiceConfigurationError` | Missing/invalid or incompatible service provider | Check `META-INF/services`, JARs, providers, and classloader |
| `ClassCastException` on identically named class | Different classloaders or incompatible types | Check classloaders of both sides and code source |
| Changed `classpath.idx` yet `spring-boot:run` unaffected | Dev run does not read the index | Run the actual executable JAR to test |
| Changing `layers.idx` does not change runtime classpath | Layer index is not the classpath index | Use the right concept and resolve dependencies |
| Classpath order differs from build script | Resolution/build config/reproducible sorting | Read the actual index inside the final archive |
| Manually edited JAR fails at runtime | Invalid Zip metadata, nested JAR format, signature/checksum, or index | Return to building from source and repackaging with the plugin |

**Do not jump to "classpath.idx caused the error" just because the file exists.** Many post-packaging bugs stem from missing dependencies, different profiles, uncopied resources, Java version mismatches, or how the container starts.

## 13. Minimal, Repeatable Diagnostic Workflow

When a Spring Boot executable JAR behaves differently from the IDE, proceed in order:

1. **Verify the exact artifact**: which JAR is the app/container actually running? Could `-plain.jar` or a cached copy be in use?
2. **Read the manifest**: do `Main-Class`, `Start-Class`, and launcher match the archive type?
3. **List the archive**: use `jar tf` to check `BOOT-INF/classes` and `BOOT-INF/lib`.
4. **Read the classpath index**: extract `BOOT-INF/classpath.idx` if present; match each name against actual JAR files.
5. **Read the dependency graph**: check Maven `dependency:tree`/Gradle `runtimeClasspath` and any exclusions/version overrides.
6. **Compare startup paths**: `java -jar` differs from IDE/`spring-boot:run`/`bootRun` in classpath construction; do not infer one from the other.
7. **Locate the class/resource**: use `CodeSource`, classloader, `-Xlog:class+load`, and `getResources` when needed.
8. **Classify the error**: missing class, binary incompatibility, duplicate class, wrong config, or different launcher.
9. **Fix in build configuration**, never edit the index directly inside a released JAR; rebuild from source.
10. **Test the actual packaged artifact** on the target JDK/container, then re-run the required suite.

### End-of-Lesson Checklist

- [ ] Understand why Spring Boot must use Loader to read nested JARs.
- [ ] Distinguish `Main-Class` = launcher from `Start-Class` = application.
- [ ] Know that `BOOT-INF/classpath.idx` contains **ordered JAR paths**, not class names.
- [ ] Know that `java -jar` is the path involving the index, whereas IDE/`bootRun`/`spring-boot:run` do not use the archive's index.
- [ ] Do not confuse classpath order with chronological class execution/loading order.
- [ ] Know that reproducible builds can sort the index alphabetically.
- [ ] Do not confuse `classpath.idx` with `layers.idx`.
- [ ] Cross-checked the index, archive contents, and dependency tree of **the same artifact**.
- [ ] Verified code source/classloader when suspecting class/resource conflicts.
- [ ] Fixed dependencies/packaging sustainably rather than hand-patching the index.

**Conclusion:** `classpath.idx` is the mechanism that lets Spring Boot Loader preserve a classpath order for an executable archive's **nested runtime JARs**. It is particularly helpful when explaining differences between `java -jar` and development runs, or tracking down duplicate class/resource issues. However, the index file **does not** manage dependencies, does not force the JVM to load all classes in line order, and does not replace verifying the actual class source.

### Official Documentation

- [Spring Boot 3.5 — Nested JARs and Classpath Index](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Maven Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Packaging](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
