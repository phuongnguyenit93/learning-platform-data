# Configuring JAR Name, Version, Classifier, and Output Location in Spring Boot (Maven and Gradle)

## 1. Lesson Goal

When packaging a Spring Boot application, a build can produce an **executable JAR** runnable with `java -jar`, alongside a **plain JAR** containing regular classes and resources. In practice, you must clearly decide:

- **Base name:** should the JAR be named after the module, the service, or something else?
- **Version:** should it appear in the JAR file name, and where does it come from?
- **Classifier:** use suffixes like `exec`, `boot`, `plain`, or no suffix to tell variants apart?
- **Output directory:** defaults are `target/` in Maven and `build/libs/` in Gradle; where do you configure custom paths like `release-build/` or `build/releases/`?
- **Distributed artifact:** how does the pipeline pick the executable JAR rather than accidentally picking the plain JAR?

Desired example where one program produces two files:

~~~text
demo-service-2.3.0.jar         # plain JAR: standard classes/resources
demo-service-2.3.0-exec.jar    # Spring Boot executable JAR
~~~

With this lesson's example configs, Maven outputs them to **release-build/** and Gradle outputs them to **build/releases/**. Giving two files the same base name does not make their contents identical.

**Versions used for illustration:** Java 17, Spring Boot 3.3.5, Gradle 8.5, Maven 3.9.x. These are example versions and must not be taken as claims about the latest releases. Each project must verify build tool, plugin, and JDK compatibility when upgrading.

## 2. Understanding the Concepts Before Renaming

### 2.1. Artifacts, JARs, and Executable JARs

A **JAR** is a ZIP-format archive containing Java classes and resources. A **Plain JAR** from the Java plugin or Maven JAR Plugin typically has a structure like:

~~~text
META-INF/MANIFEST.MF
com/example/demo/ArtifactNamingApplication.class
application.properties
~~~

A **Spring Boot executable JAR** is packaged by **spring-boot:repackage** (Maven) or **bootJar** (Gradle), typically structured as:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/demo/ArtifactNamingApplication.class
BOOT-INF/lib/...
~~~

The executable JAR contains the launcher and required runtime dependencies, so it can run with **java -jar** when configured with the right main class. The plain JAR from this simple example is **not** an executable Boot JAR; it does not carry all application dependencies and should not be chosen for deployment merely because it also ends in `.jar`.

**The classifier is not what makes a JAR runnable.** A classifier is just a naming/attribute label to distinguish artifacts. Executability comes from how the plugin **packages contents and the manifest**, not from the `-exec` string.

### 2.2. File Name vs. Artifact Coordinates

In Maven, coordinates typically consist of:

~~~text
groupId : artifactId : version [: classifier] : type
~~~

Example:

~~~text
com.example : jar-naming-demo : 2.3.0 : exec : jar
~~~

- **groupId** identifies the publishing group or namespace.
- **artifactId** identifies the module.
- **version** is the artifact version in the Maven repository.
- **classifier** is an optional label for an attached variant.
- **type** is usually `jar`, though other artifact types exist.

In Gradle, `group` and `version` also serve as project metadata. **Local file names** and **published coordinates** are related yet not identical. Specifically, changing **Maven `build.finalName`** **does not change** `artifactId` or `version` in the POM.

### 2.3. Four Parts of a File Name

A common convention is:

~~~text
<baseName>-<version>-<classifier>.jar
~~~

When there is no classifier, drop both the hyphen and classifier value:

~~~text
demo-service-2.3.0.jar
~~~

With classifier `exec`:

~~~text
demo-service-2.3.0-exec.jar
~~~

Gradle also supports an **appendix** and custom extension via archive task APIs; the typical order is **baseName, appendix, version, classifier, extension**. Maven primarily constructs names from **finalName + classifier + extension** for the corresponding JAR plugin. These are **file-naming** rules; do not infer every detail of Maven/Gradle publishing solely from file names.

## 3. How Do Maven and Gradle Defaults Differ?

| Aspect | Maven with Spring Boot Parent | Gradle with Spring Boot Plugin |
| --- | --- | --- |
| Application version | `<project><version>...` | `version = '...'` |
| Artifact base name | `artifactId` | Usually from `project.name` / base archives name |
| Default file name | `artifactId-version.jar` | `name-version.jar` |
| Output directory | `target/` | `build/libs/` |
| Creating plain JAR | `maven-jar-plugin` in `package` lifecycle | `jar` task |
| Creating Boot JAR | `spring-boot:repackage` goal | `bootJar` task |
| Default Boot JAR classifier | None; Boot replaces main JAR | Usually **none** |
| Default plain JAR classifier | No classifier needed when using main JAR alone; when repackaging without classifier, original is backed up as `.original` | **plain** per Spring Boot convention |
| Changing file name | `<build><finalName>` | `archiveBaseName`, `archiveVersion`, `archiveClassifier`, `archiveFileName` |
| Changing build/artifact directory | `<build><directory>` or plugin-specific `outputDirectory` | `destinationDirectory` on archive tasks |

**Important:** the Spring Boot Gradle Plugin normally configures **jar** with the `plain` classifier so it can be built alongside **bootJar**. The Maven Spring Boot Plugin **does not do the same by default**: when repackaging without a classifier, the executable Boot JAR replaces the main artifact and the original JAR may remain on disk with `.original`. Therefore, never apply one single naming rule across both tools without explicit configuration.

## 4. Maven: `finalName`, `project.version`, `classifier`, and `build.directory`

### 4.1. Maven Defaults Without Special Configuration

Given a POM:

~~~xml
<groupId>com.example</groupId>
<artifactId>jar-naming-demo</artifactId>
<version>2.3.0</version>
~~~

This is a **POM snippet**, not a complete `pom.xml`. By convention, the basic JAR path is:

~~~text
target/jar-naming-demo-2.3.0.jar
~~~

`project.version` is **2.3.0**. The **Spring Boot Plugin** version (e.g., **3.3.5**) does not become the application version: `3.3.5` is the tool/framework version, while `2.3.0` is your project's product version.

### 4.2. Changing the Local Filename with `build.finalName`

In `pom.xml`:

~~~xml
<build>
    <finalName>demo-service-2.3.0</finalName>
</build>
~~~

This names the JAR **demo-service-2.3.0.jar** inside the configured build directory. However, hardcoding `2.3.0` means that bumping the project version to `2.4.0` **leaves the filename at 2.3.0** if you forget to update it.

Reference the project version instead:

~~~xml
<build>
    <finalName>demo-service-${project.version}</finalName>
</build>
~~~

Accordingly, if the POM version is 2.3.0, `finalName` interpolates to **demo-service-2.3.0**.

**Note:** `finalName` is only the name **without the `.jar` extension**. Do not put `demo-service.jar` into `finalName` expecting Maven not to append `.jar`. Furthermore, `finalName` is a build output setting, **not a change to Maven coordinates**; during `mvn install/deploy`, repository names still follow `artifactId`/`version`/`classifier`.

### 4.3. Changing the Output Directory with `build.directory`

Maven uses `project.build.directory` as its main output directory. To move from `target/` to **release-build/** under the project root:

~~~xml
<build>
    <directory>${project.basedir}/release-build</directory>
    <finalName>demo-service-${project.version}</finalName>
</build>
~~~

Then, at version 2.3.0, the JAR is created in:

~~~text
release-build/demo-service-2.3.0.jar
~~~

Yet `<directory>` **does more than move JARs**. It moves **Maven's entire build directory**, meaning other outputs like `classes`, `test-classes`, plugin reports, and intermediate files also move from `target/` to `release-build/`. If CI reads `target/surefire-reports`, `target/classes`, or `target/*.jar`, update those paths after changing `directory`.

**Changing `build.directory` is not always ideal.** If you simply want release artifacts collected in a dedicated folder while keeping Maven's standard lifecycle layout, use a **CI artifact copy/publish step** or a plugin's specific `outputDirectory`, and carefully verify what gets installed/deployed. The lab below uses `build.directory` because it is straightforward and keeps both plain and `exec` JARs in the same place.

### 4.4. Spring Boot Maven Plugin: Using `classifier` to Distinguish the Executable JAR

The Spring Boot plugin runs the `repackage` goal to turn the JAR produced by `package` into an executable archive. When **no classifier is configured**, the executable replaces the main JAR:

~~~text
target/jar-naming-demo-2.3.0.jar          # executable Boot JAR
target/jar-naming-demo-2.3.0.jar.original # original saved in local build
~~~

`.original` is not a Maven classified variant published automatically and should not be deployed.

When configuring **classifier `exec`**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

... Maven can keep **two artifacts**:

~~~text
demo-service-2.3.0.jar        # plain JAR / main artifact
demo-service-2.3.0-exec.jar   # executable Spring Boot JAR
~~~

With `spring-boot-starter-parent`, the **repackage** goal is already configured in the inherited execution; adding the plugin with `classifier` as above suffices for this example. Without the Boot parent, you must **bind the `repackage` goal to the `package` lifecycle** properly, because merely adding versions/dependencies to the POM will not invoke `repackage`.

**Important detail:** the Spring Boot Maven Plugin's `classifier` also participates in **selecting the input source for repackaging**. If the Maven project already produced an input JAR carrying classifier `exec`, the plugin may pick that artifact to repackage; otherwise, it uses the main archive and attaches the Boot archive under classifier `exec`. Thus, in complex builds, avoid accidental classifier collisions across multiple packaging plugin executions.

### 4.5. How Do `attach` and `classifier` Relate to `install`/`deploy`?

The Spring Boot Maven Plugin has an `attach` property (default **true**). When the executable Boot JAR has **classifier `exec`**, the plugin can attach it as a **supplemental artifact** so `mvn install` or `mvn deploy` publishes it alongside the main JAR.

Conceptual example:

~~~text
com.example:jar-naming-demo:2.3.0       → main/plain JAR
com.example:jar-naming-demo:2.3.0:exec  → executable Boot JAR
~~~

With `<attach>false</attach>`, the repackaged JAR is still built for local use, yet **is not attached for `install`/`deploy`** per default plugin behavior.

This is useful when one module serves as both a Java library and an executable demo. The **plain JAR** places classes at standard paths suitable as a dependency; the **Boot JAR** puts classes under `BOOT-INF/classes`, so it **should not** be used as a traditional library JAR for other modules.

## 5. Maven: Complete `pom.xml` Producing Two Clearly Named JARs

Create a project directory **jar-naming-demo** and save this `pom.xml` at the root:

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
    <artifactId>jar-naming-demo</artifactId>
    <version>2.3.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <directory>${project.basedir}/release-build</directory>
        <finalName>demo-service-${project.version}</finalName>

        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <classifier>exec</classifier>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Line-by-line explanation of naming/version/path settings:**

1. `artifactId = jar-naming-demo` is the Maven module identifier. It **is not altered** by `finalName`.
2. `version = 2.3.0` is the project/artifact version.
3. `packaging = jar` requests a JAR build; this is the default for many Maven Java projects, written explicitly for clarity.
4. `java.version = 17` is the Java baseline for this Spring Boot 3.x example, **not** the artifact version.
5. `directory = .../release-build` sets the shared Maven output directory.
6. `finalName = demo-service-\${project.version}` dynamically injects the POM version into the file name. In this example, the effective value is `demo-service-2.3.0`.
7. `classifier = exec` produces the **repackaged executable JAR** with the `-exec` suffix while keeping the main JAR plain.

Because the Boot parent already configures the `repackage` execution, this POM does not declare it again. With a different parent, add the execution in the `package` phase per Spring Boot docs.

### 5.1. Complete Java 17 Application Code

Create **src/main/java/com/example/demo/ArtifactNamingApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArtifactNamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArtifactNamingApplication.class, args);
    }

    @Bean
    CommandLineRunner printArtifactName() {
        return args -> System.out.println("JAR_NAMING_OK");
    }
}
~~~

This is a runnable Spring Boot app with Java 17 and the basic starter; it opens no HTTP server, needs no database, and needs no `application.properties`. It prints one line to verify the executable JAR actually boots.

### 5.2. Maven Build and Expected Outputs

From the project root:

~~~bash
./mvnw clean package
~~~

If there is no Maven Wrapper yet, use a compatible installed Maven:

~~~bash
mvn clean package
~~~

On Windows use **mvnw.cmd** instead of **./mvnw**. After a successful build, **release-build/** contains:

~~~text
release-build/
├── classes/
├── generated-sources/                 # depends on plugins
├── demo-service-2.3.0.jar             # plain JAR
└── demo-service-2.3.0-exec.jar        # executable Boot JAR
~~~

Intermediate folders can vary by Maven/plugin version, yet **those two JAR names** are what to verify under this lesson's configuration. If a project uses extra packaging plugins, additional artifacts may appear—always check classifiers carefully.

Run the **right** executable JAR:

~~~bash
java -jar release-build/demo-service-2.3.0-exec.jar
~~~

Aside from Spring Boot startup logs, the line printed by the **program itself** is:

~~~text
JAR_NAMING_OK
~~~

The command below is **not a guaranteed way** to run the plain JAR:

~~~bash
java -jar release-build/demo-service-2.3.0.jar
~~~

The plain JAR was not repackaged by Boot, so it lacks the same bootstrap/dependency layout. Depending on the manifest, it may report a missing `Main-Class` or missing classes/dependencies. Do not try to fix it merely by renaming the file to `-exec.jar`.

### 5.3. Why Avoid Hardcoding a Fixed Version in `finalName`?

Suppose you bump the POM version from **2.3.0** to **2.4.0**:

- With `<finalName>demo-service-\${project.version}</finalName>`: the JAR name updates automatically to **demo-service-2.4.0-exec.jar**.
- With `<finalName>demo-service-2.3.0</finalName>`: the JAR name stays **2.3.0**, even though the Maven artifact is **2.4.0**.

In CI/CD, that mismatch easily causes pipelines to pick up a stale artifact. Dynamic version filenames aid traceability, alongside clean builds and purging old artifacts before distribution.

## 6. Maven: Choosing a Separate `outputDirectory` for `repackage` When Truly Needed

The Spring Boot Maven Plugin provides an **outputDirectory** parameter on the `repackage` goal. Example **plugin configuration fragment**, not a complete POM:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
        <outputDirectory>${project.build.directory}/delivery</outputDirectory>
    </configuration>
</plugin>
~~~

Meaning:

- `project.build.directory` is the general build directory, defaulting to `target` or overridden via `<build><directory>`.
- `outputDirectory` controls where the plugin **writes the repackaged archive**.
- This setting **does not change** where the Maven JAR Plugin writes the plain JAR or where other Maven tasks store outputs.

This snippet is an **alternative** to Section 5's plugin configuration, not something to add in duplicate alongside it. When separating the Boot archive path from the main JAR, run **package/verify**, check the actual files, and also test **install/deploy** if publishing artifacts; artifact attachment, copy steps, and CI paths must stay aligned.

**Recommendation:** if you just want release artifacts placed into a CI-managed delivery folder, it is usually easier to keep `target/` and have CI copy/upload **the exact executable JAR**. Changing `outputDirectory` does not change Maven GAV coordinates or automatically update paths hardcoded in Dockerfiles/pipelines.

## 7. Gradle: Distinguishing Archive Properties on `bootJar` and `jar`

Gradle's Java Plugin provides the **jar** task; the Spring Boot Gradle Plugin adds **bootJar** when the Java plugin is applied. `BootJar` extends `Jar`, sharing archive naming and location properties.

| Gradle Property | Purpose |
| --- | --- |
| **archiveBaseName** | Base name, e.g., `demo-service`. |
| **archiveAppendix** | Optional segment after `baseName`. |
| **archiveVersion** | Version segment in the file name. |
| **archiveClassifier** | Variant label, e.g., `exec` or `plain`. |
| **archiveExtension** | Archive extension, typically `jar` for JARs. |
| **archiveFileName** | Full file name, overriding the composed pattern above. |
| **destinationDirectory** | Directory containing the archive file. |
| **archiveFile** | Provider for the resulting file, derived from `destinationDirectory` and `archiveFileName`. |

Example composition without an appendix:

~~~text
archiveBaseName  = demo-service
archiveVersion   = 2.3.0
archiveClassifier= exec
archiveExtension = jar

=> demo-service-2.3.0-exec.jar
~~~

With an empty classifier, the JAR becomes `demo-service-2.3.0.jar`. To omit the version from the filename, you can set **archiveVersion** to empty per task, though doing so **does not** change `project.version` used in publication metadata.

### 7.1. Default Classifiers in Spring Boot Gradle

Per Spring Boot Gradle Plugin convention:

~~~text
bootJar → <name>-<version>.jar
jar     → <name>-<version>-plain.jar
~~~

When both tasks exist, `jar` gets the **plain** classifier to prevent colliding with `bootJar`. To give the **exec JAR a classifier** and leave the **plain JAR unclassified**, configure:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier.set('exec')
}

tasks.named('jar') {
    archiveClassifier.set('')
}
~~~

This is a **`build.gradle` snippet**, not a complete standalone project config. Because both tasks produce different file names, they can write to the same directory safely.

**Collision warning:** never give **bootJar** and **jar** the exact same `archiveFileName` and `destinationDirectory`, or both tasks will write to the same path. The outcome depends on which task runs last and can corrupt builds, build caches, or publications. Keep at least one naming segment distinct.

## 8. Gradle: Complete `build.gradle` with Custom Naming and Output Directory

**settings.gradle** file:

~~~groovy
rootProject.name = 'jar-naming-demo'
~~~

**build.gradle** file (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '2.3.0'

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
}

tasks.named('bootJar') {
    archiveBaseName.set('demo-service')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('exec')
    destinationDirectory.set(layout.buildDirectory.dir('releases'))
}

tasks.named('jar') {
    archiveBaseName.set('demo-service')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('plain')
    destinationDirectory.set(layout.buildDirectory.dir('releases'))
}
~~~

This is the **complete `build.gradle`** for the example using Java 17. It needs a compatible Gradle Wrapper or Gradle 8.5 installed; if Gradle cannot locate a matching JDK 17, install the right Java version or configure a toolchain resolver.

**Explanation:**

1. `group` and `version` are project metadata; version **2.3.0** serves artifact/dependency management.
2. `bootJar` creates the executable JAR with classifier **exec**, named **demo-service-2.3.0-exec.jar**.
3. `jar` creates the plain JAR with classifier **plain**, named **demo-service-2.3.0-plain.jar**.
4. Both use `layout.buildDirectory.dir('releases')`, so outputs land in **build/releases/** rather than the default **build/libs/**.
5. `archiveVersion.set(project.version.toString())` keeps the filename version synchronized with `project.version`. Changing `version='2.4.0'` updates both filenames on the next build.
6. `archiveBaseName` only sets the file name segment; it does not overwrite `rootProject.name` in `settings.gradle` or default module publication coordinates.
7. `archiveClassifier` is solely a variant label; **it does not directly change which Java classes compile or the task's packaging layout**.

**Difference from Maven in this example:** in Gradle, the plain JAR keeps the **-plain** suffix, whereas Maven left the plain JAR unclassified. If you want both tools to produce the exact same two filenames as in Section 1, change **jar.archiveClassifier** from `plain` to empty string `''`. Gradle will then output:

~~~text
build/releases/demo-service-2.3.0.jar
build/releases/demo-service-2.3.0-exec.jar
~~~

Choosing `plain` versus empty depends on your project's distribution conventions. There is no hard rule that a plain JAR must always carry a `plain` suffix.

### 8.1. Sharing the Same Java Program

Create **src/main/java/com/example/demo/ArtifactNamingApplication.java** with the full contents:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArtifactNamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArtifactNamingApplication.class, args);
    }

    @Bean
    CommandLineRunner printArtifactName() {
        return args -> System.out.println("JAR_NAMING_OK");
    }
}
~~~

This Java class is **identical** to the Maven version; only the build configuration and output path change.

### 8.2. Gradle Build and Expected Output Files

~~~bash
./gradlew clean build
~~~

Or when building only the Boot JAR:

~~~bash
./gradlew clean bootJar
~~~

**Distinction:** `build` runs the `assemble`/`check` lifecycle so it normally builds both `jar` and `bootJar` per the standard task graph; `bootJar` only requests the executable archive and its required dependencies. Do not assume `bootJar` always runs plain `jar` unless a task dependency exists.

After a **clean build**, observe the files:

~~~text
build/
└── releases/
    ├── demo-service-2.3.0-exec.jar     # bootJar
    └── demo-service-2.3.0-plain.jar    # jar
~~~

Run the application:

~~~bash
java -jar build/releases/demo-service-2.3.0-exec.jar
~~~

Aside from Boot logs, the line printed by the program itself is:

~~~text
JAR_NAMING_OK
~~~

If no wrapper exists on the machine, run `gradle clean build` with a compatible Gradle installed. On Windows use **gradlew.bat**; relative paths to the JAR can use forward slashes or backslashes depending on the shell.

## 9. `archiveFileName`: When an Exact Fixed File Name Is Needed

Sometimes a deployment platform expects **app.jar** instead of a versioned name. Gradle lets you set it directly:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('app.jar')
    destinationDirectory.set(layout.buildDirectory.dir('delivery'))
}
~~~

This is a **`build.gradle` fragment**; it overrides how `bootJar`'s name is formed without altering `project.version`. The Boot JAR is written to **build/delivery/app.jar**.

**Key point to remember:** once a fixed `archiveFileName` is set, changing `archiveBaseName`, `archiveVersion`, or `archiveClassifier` **no longer updates the overridden filename**. If you want a versioned filename, configure the individual segments (`archiveBaseName`, `archiveVersion`, `archiveClassifier`) or construct a deliberate `Provider` value.

If `jar` is also configured to output **app.jar** in **build/delivery/**, the two tasks collide. Give the plain JAR a different name or publish only the executable Boot JAR per pipeline requirements.

**Should you drop the version from the filename?** You can if the deployment target requires a fixed filename and the version is tracked in registry tags/manifests/metadata, though uploads should still attach **checksums and version metadata** so overwriting an old artifact never destroys traceability.

## 10. `base.archivesName` and Configuring Multiple Gradle Tasks

In Gradle, you can set the base name across archive tasks through the `base` plugin extension, for example:

~~~groovy
base {
    archivesName = 'demo-service'
}
~~~

This is a **Groovy DSL fragment in `build.gradle`**. It sets the **convention** for archive tasks that honor it. However, if a specific task sets `archiveBaseName.set('...')`, the explicit per-task value wins.

For an application with both `jar` and `bootJar`:

- Use **base.archivesName** when you want a shared base name.
- Use **tasks.named('bootJar')** when customizing only the executable archive.
- Use **tasks.named('jar')** when customizing only the plain archive.
- Use **destinationDirectory** per task when output directories differ.

Example fragment configuring a shared base while keeping distinct classifiers:

~~~groovy
base {
    archivesName = 'billing-service'
}

tasks.named('bootJar') {
    archiveClassifier.set('exec')
}

tasks.named('jar') {
    archiveClassifier.set('plain')
}
~~~

With `version='2.3.0'` and default `destinationDirectory`, expected outputs:

~~~text
build/libs/billing-service-2.3.0-exec.jar
build/libs/billing-service-2.3.0-plain.jar
~~~

Avoid configuring `base` and setting conflicting per-task names simultaneously without good reason: it makes final filenames harder for readers to predict.

## 11. Verifying Artifacts Instead of Guessing from Names

### 11.1. Listing JAR Files After Building

Maven:

~~~bash
./mvnw clean package
~~~

Then inspect **release-build/** using a file explorer, `ls` (Linux/macOS), or `dir` (Windows). With Section 5's POM, expect these two files:

~~~text
release-build/demo-service-2.3.0.jar
release-build/demo-service-2.3.0-exec.jar
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

With Section 8's `build.gradle`, expect these two files:

~~~text
build/releases/demo-service-2.3.0-plain.jar
build/releases/demo-service-2.3.0-exec.jar
~~~

### 11.2. Inspecting JAR Contents with the JDK Tool

Use `jar tf`, included with the JDK.

Maven Boot JAR:

~~~bash
jar tf release-build/demo-service-2.3.0-exec.jar
~~~

Maven plain JAR:

~~~bash
jar tf release-build/demo-service-2.3.0.jar
~~~

Gradle Boot JAR:

~~~bash
jar tf build/releases/demo-service-2.3.0-exec.jar
~~~

Gradle plain JAR:

~~~bash
jar tf build/releases/demo-service-2.3.0-plain.jar
~~~

**Typical indicators:**

- The executable Spring Boot JAR contains `BOOT-INF/classes/`, `BOOT-INF/lib/`, and the version-matching Boot launcher.
- The plain JAR contains `com/example/demo/ArtifactNamingApplication.class` at the standard classpath location and lacks the Boot archive's nested dependency/runtime layout.

For JARs with non-default layouts or specialized packaging configurations, cross-check against plugin config. Never rely on the `exec` classifier string alone to guarantee an archive runs.

### 11.3. Running the Right Executable Archive

~~~bash
java -jar release-build/demo-service-2.3.0-exec.jar
~~~

Or:

~~~bash
java -jar build/releases/demo-service-2.3.0-exec.jar
~~~

**Run only the command matching your chosen build tool.** The first is for Maven, the second for Gradle. Seeing `JAR_NAMING_OK` confirms the real artifact launches on the active Java runtime; add functional tests if you want to verify full app behavior.

### 11.4. Gradle: Inspecting the Archive File Path via Provider

In `build.gradle`, you can add a diagnostic task:

~~~groovy
tasks.register('showBootJarPath') {
    doLast {
        println(tasks.named('bootJar').get().archiveFile.get().asFile)
    }
}
~~~

Then run:

~~~bash
./gradlew -q showBootJarPath
~~~

The task prints the **expected file path** computed from `destinationDirectory` and `archiveFileName`. It **does not build the JAR** because this task has no `dependsOn('bootJar')`. Even if the file does not exist yet, the path still prints; to verify the actual artifact, run `bootJar` and inspect the file.

## 12. File Names, Versions, and CI/CD

### 12.1. Do Not Use Wildcards That Mix Up Plain and Boot JARs

A Docker/CI selection using a wildcard:

~~~text
build/releases/*.jar
~~~

... matches **both the executable JAR and the plain JAR**. Glob ordering is not a rule for choosing the right artifact. A pipeline can accidentally copy or publish the plain JAR.

**Be explicit:**

~~~text
build/releases/demo-service-2.3.0-exec.jar
~~~

Or, in CI systems capable of reading task outputs from Gradle, consume **bootJar.archiveFile** directly or the exact path declared on the task.

**Maven** follows the same rule: select `release-build/demo-service-2.3.0-exec.jar`, never the first match in `release-build/*.jar`.

### 12.2. Fixed Filename or Versioned Filename?

| Purpose | Recommendation |
| --- | --- |
| Artifacts archived in repository/CI | Include version or build ID; prevent accidental overwrites |
| Docker build stage | Copy a clearly classified/versioned file to a stable path inside the image, e.g., `app.jar` |
| Maven library publication | Keep proper Maven coordinates; select main/plain JAR for consumers |
| Spring Boot executable deployment | Use the exact Boot JAR with a clear classifier or naming convention |
| Rolling artifact deployments | Track version, checksum, provenance, and the commit that built the filename |

A common workflow: the build produces **demo-service-2.3.0-exec.jar**, CI uploads it with `version=2.3.0` metadata, and the Dockerfile copies **that exact file** into the image at a stable path `/app/app.jar`. **Renaming the file during the container copy step** does not alter its contents or original Maven coordinates.

### 12.3. Distinguishing Project Version from Plugin Version

In our example:

~~~text
Project/application version : 2.3.0
Spring Boot plugin version  : 3.3.5
Java toolchain version      : 17
Archive classifier         : exec
~~~

These are **four separate pieces of metadata**. `demo-service-2.3.0-exec.jar` carries **2.3.0** because the project chose it, not because the Spring Boot plugin defaults to `3.3.5`. JDK 17 does not appear in the filename unless you intentionally add it to an appendix or classifier.

### 12.4. Build Reproducibility

Identical file names **do not prove byte-for-byte identical contents**. JAR contents can vary due to code, dependencies, timestamps, entry order, or environment-generated resources. The Spring Boot Maven Plugin supports **outputTimestamp**; Gradle archive tasks offer settings for reproducible file order and preserving timestamps. When checksum reproducibility is needed, pin dependency/plugin versions, run clean builds, and verify deterministic code/resource generation.

Do not base versioned filenames solely on wall-clock timestamps in CI without accompanying metadata. Versions, commit SHAs, and checksums provide far clearer traceability.

### 12.5. Upload, Install, and Publish Do Not Depend Only on Local Paths

- **Maven:** `mvn install`/`mvn deploy` publishes based on artifact coordinates and attached artifacts. `finalName` changes the local file name without changing `artifactId`/`version` in the repository. Classifier `exec` appears as an attached artifact when `attach=true`.
- **Gradle:** `bootJar` and `jar` create local files; publishing via `maven-publish` requires configuring the matching publication/artifacts. **Do not assume** Gradle publishes the executable Boot JAR simply because `bootJar` produced a file.
- **CI/CD artifact upload:** point to the verified output. Changing `destinationDirectory` without updating the pipeline causes "file not found" errors or uploads a stale artifact.

## 13. Configuration Scenarios Worth Considering

### 13.1. Only Needing the Executable Spring Boot JAR

If an application has zero need for a plain JAR, in Gradle you can disable the plain task:

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

**Caution:** do not disable `jar` mechanically if the project uses a native image plugin or other integrations that depend on the plain JAR. Spring Boot documentation specifically warns about this in certain native image setups. In Maven, when `repackage` uses no classifier, the executable replaces the main artifact; no equivalent task-disabling step is needed.

### 13.2. Needing Both a Library JAR and an Executable JAR

Maven: use **classifier `exec`** for the Boot archive and keep the main JAR for other modules to depend on. This works well when one module must both publish classes in standard Java layout and provide a runnable demo entry point, though architecturally it is often cleaner to split library and application into two modules.

Gradle: `jar` builds the plain archive; `bootJar` builds the executable archive. To publish both, design publications and classifiers per consumer requirements rather than merely tweaking filenames.

### 13.3. Multi-Module Builds

Suppose Gradle has **:app** and **:core**. Typically only `:app` applies `org.springframework.boot` and builds `bootJar`. `:core` uses `java-library` and builds a plain JAR without needing `bootJar`. If every subproject sets `archiveBaseName='demo-service'` with the same version into a shared output directory, they risk **filename collisions**.

In multi-project builds:

- Keep distinct base names per module, or use per-project `destinationDirectory` paths.
- When aggregating module artifacts into one distribution directory, include module names or classifiers as needed.
- Never apply the Boot plugin blanket-style to library modules just "to get a JAR".
- In Maven multi-module builds, a parent POM's `finalName` can be inherited; if it hardcodes one name for all modules sharing a `build.directory`, conflicts can occur. Check each module's effective POM and build output.

### 13.4. Changing the Whole Gradle Build Directory vs. Only `destinationDirectory`

Gradle allows configuring **layout.buildDirectory** globally, yet doing so relocates **many kinds of outputs**: classes, resources, test results, reports, and artifacts. If your goal is only the JARs, setting **destinationDirectory** on `bootJar`/`jar` is usually enough. This mirrors Maven's distinction between `build.directory` and a plugin-specific `outputDirectory`.

### 13.5. Bumping the Project Version

When bumping project version from 2.3.0 to 2.4.0:

~~~text
Maven project.version 2.4.0      → demo-service-2.4.0-exec.jar
Gradle project.version 2.4.0     → demo-service-2.4.0-exec.jar
~~~

In both setups, the versioned filenames update automatically because configuration references the project version. Remember that repository coordinates also change version; bumping a version does more than prettify a filename.

## 14. Common Errors and How to Solve Them

**1. JAR file has the wrong version in its name.** Check `pom.xml` `<version>` or Gradle `version = '...'`, then check whether `finalName`/`archiveVersion` hardcodes an old version. In Gradle, once a fixed `archiveFileName` is set, `archiveVersion` no longer controls the filename.

**2. No JAR appears in `target/` or `build/libs/`.** You may have changed `build.directory`, plugin `outputDirectory`, or `destinationDirectory`. Check the POM/build script and task output; do not assume it is a compile error.

**3. Two JARs exist and the plain JAR was picked to run.** Check classifiers/tasks, inspect `jar tf` for `BOOT-INF/classes`, and run `java -jar` on the executable. Never treat `.jar` as proof of executability.

**4. Maven produces `.jar.original`.** This is normally the original JAR preserved by Spring Boot `repackage` when no classifier is set. Do not treat it as a published artifact. If both variants are needed cleanly, use `classifier exec`.

**5. Maven builds only a plain JAR, no executable.** Verify `spring-boot-maven-plugin` is declared properly and the `repackage` execution ran during the `package` lifecycle; when using a parent other than `spring-boot-starter-parent`, bind the `repackage` goal explicitly.

**6. Setting a classifier in `maven-jar-plugin` without syncing Spring Boot `repackage`.** The Maven Boot Plugin uses `classifier` when choosing its source artifact. If multiple plugins set classifiers without coordinating execution order, results can surprise you. Keep attachment design clear and inspect the actual archive.

**7. Editing `finalName` expecting Maven repository coordinates to change.** Published coordinates still rely on `groupId`/`artifactId`/`version`/`classifier`. To change the real `artifactId`, update the POM and consumers; `finalName` only affects local build file names.

**8. Gradle `bootJar` and `jar` overwrite each other.** Both tasks share the same `archiveFileName` and `destinationDirectory`. Give them distinct classifiers (`exec`/`plain`) or distinct directories; clean and rebuild to remove stale files.

**9. Gradle adds `-plain` even when unconfigured.** The Spring Boot Gradle Plugin configures the `plain` convention classifier on `jar` to avoid colliding with `bootJar`. This is normal behavior, not a broken filename.

**10. Removing the classifier from `bootJar` without checking `jar`.** If `jar` keeps `plain`, there is no collision; if `jar` is also empty and shares `destinationDirectory`, they collide. Check all archive tasks rather than `bootJar` alone.

**11. Running only `bootJar` and wondering why the plain JAR is missing.** `bootJar` does not depend on `jar`. To build both, run `build`/`assemble` per the task graph or explicitly `jar bootJar`.

**12. CI uses glob `build/libs/*.jar` and runs the wrong file.** Switch the pipeline to an explicit path or read the artifact path from the task; update paths whenever `destinationDirectory` changes.

**13. Changing Maven `build.directory` breaks report paths in `target/`.** Classes and test reports move too; update CI tool paths or consider copying the artifact instead of relocating the entire build directory.

**14. Using `archiveFileName='app.jar'` yet expecting the version in the filename.** Fixed `archiveFileName` overrides composed naming. To include the version, use `archiveVersion` or construct dynamic filenames intentionally.

**15. Incompatible Java runtime.** Classes compiled with Java 17 require a sufficiently new Java runtime; a classifier named `java17` does not control classfile bytecode version. Check Gradle toolchain/Maven compiler release and production JVM version.

**16. JAR has `BOOT-INF` yet still fails to boot.** Check main class, manifest/launcher, runtime dependencies, application configuration, and error logs. A structurally valid-looking archive does not guarantee every dependency was packaged.

**17. Publisher only uploads the plain JAR even though `bootJar` exists.** Maven needs proper `attach`/classifier config; Gradle publishing needs proper artifact/publication config. Never treat local filenames as proof of publication.

**18. Version contains `SNAPSHOT`.** In Maven, `version=2.3.0-SNAPSHOT` generates `demo-service-2.3.0-SNAPSHOT-exec.jar` locally per `finalName`, yet snapshot repositories may store timestamped filenames per retention policy. CI should not infer remote filenames purely from local filenames.

**19. Reusing the exact same filename across deployments makes rollbacks hard.** Use version/commit IDs, immutable registry paths, checksums, and metadata instead of repeatedly overwriting a single `app.jar`.

**20. Setting Boot's `outputDirectory` separately without updating the Dockerfile path.** Check which file is actually produced and update build context/upload paths; never treat a stale JAR's presence as proof the latest build succeeded.

## 15. Hands-On and Release Checklist

- [ ] Clearly identify which JAR is the **executable Boot JAR** and which is the **plain JAR**.
- [ ] Distinguish **project version**, **Spring Boot plugin version**, and **Java version**.
- [ ] For Maven: decide `artifactId`, `version`, `build.finalName`, `build.directory`, and `spring-boot-maven-plugin.classifier`.
- [ ] For Maven: if using the Boot parent, verify `repackage` execution; if not, bind `repackage` into the lifecycle.
- [ ] For Gradle: configure `archiveBaseName`, `archiveVersion`, `archiveClassifier`, and `destinationDirectory` on `bootJar`/`jar` as needed.
- [ ] Prevent any two archive tasks from writing to the same file path.
- [ ] Use dynamic versions in filenames when tracing artifacts across releases.
- [ ] Run a clean build and list generated file paths.
- [ ] Use `jar tf` to distinguish Boot layout from plain layout.
- [ ] Run **the right executable JAR** with `java -jar` and verify stdout/startup.
- [ ] Sync Dockerfile/CI artifact globs whenever filenames or directories change.
- [ ] When publishing, verify **Maven attached artifacts** or **Gradle publications** accordingly.
- [ ] Record version/commit/checksum metadata for traceability and rollback.

## 16. Official Reference Documentation

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven — POM Reference (build.directory, finalName): https://maven.apache.org/pom.html
- Gradle — Jar Task API (archiveBaseName, archiveVersion, archiveClassifier, archiveFileName, destinationDirectory): https://docs.gradle.org/8.5/dsl/org.gradle.jvm.tasks.Jar.html
- Gradle — Working with Files and Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Spring Boot 3.3 — Gradle Plugin Publishing: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html

**Conclusion:** To control the name, version, classifier, and output location of Spring Boot JARs, first establish **whether an artifact is executable or plain**. Maven uses **version + `build.finalName` + `build.directory` + `spring-boot-maven-plugin.classifier`**; Gradle uses **archive properties on `bootJar` and `jar`**, especially **`archiveBaseName`, `archiveVersion`, `archiveClassifier`, and `destinationDirectory`**. After any change, verify **the actual file, JAR contents, and launch command**, then update CI/CD with exact paths instead of relying on wildcards.