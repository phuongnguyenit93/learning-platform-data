# Automatic Main Class Detection and Configuration with Multiple Entry Points in Spring Boot

## 1. Goal and Problem Statement

When packaging a Spring Boot project as an **executable JAR**, Maven or Gradle needs to know **which Java class contains the application entry point**. With a single class containing `public static void main(String[] args)`, the build tool can usually detect it automatically. However, when a repository has multiple main classes—such as an API application, a batch job, a CLI tool, or helper code—auto-detection can become ambiguous or pick the wrong class.

After this lesson, you will be able to:

1. Explain the **application main class**, how the Spring Boot Maven/Gradle plugin finds it, and the limits of auto-detection.
2. Distinguish the manifest's **`Main-Class`** (Spring Boot launcher) from **`Start-Class`** (the main class you wrote) in an executable JAR.
3. Explicitly configure the main class for the **Maven Spring Boot Plugin** (`start-class` when inheriting from the Parent, `mainClass` when configuring directly) and the **Gradle Spring Boot Plugin** (`springBoot.mainClass`, `bootJar.mainClass`, `bootRun.mainClass`).
4. Design and run a Java 17+ project with **two entry points**, verifying which class gets packaged and executed.
5. Evaluate when to use one JAR with one entry point versus splitting into multiple modules/artifacts; avoid releasing JARs with different contents under the same name/version.
6. Diagnose errors such as "main class not found", "unable to determine main class", wrong manifest, or JAR failing to run with `java -jar`.

**Example assumptions:** Spring Boot **3.3.5**, Java **17**, and a compatible Maven Wrapper or Gradle Wrapper. Versions are used for consistent illustration, **not as a directive to upgrade real projects to this release**. For other Spring Boot releases, always consult version-specific documentation because some launcher names and main-class precedence rules have changed over time.

## 2. Three "Main" Concepts That Are Easy to Confuse

### 2.1. Java Application Main Method

Example Java class with an entry point:

~~~java
package com.example.demo;

public class DemoApplication {
    public static void main(String[] args) {
        System.out.println("ENTRY=DEMO");
    }
}
~~~

This is a standalone Java class that can be executed directly. The file must reside at `src/main/java/com/example/demo/DemoApplication.java` in a Maven/Gradle project, or be compiled and run directly with the JDK:

~~~bash
javac -d out src/main/java/com/example/demo/DemoApplication.java
java -cp out com.example.demo.DemoApplication
~~~

Exact output:

~~~text
ENTRY=DEMO
~~~

The standard Java main signature is **`public static void main(String[] args)`** (or an equivalent parameter declaration like `String... args`). A method named `main` that is non-`static`, has wrong parameters, or is inaccessible is not a standard entry point that the plugins in this example look for.

### 2.2. Spring Boot Application Class

A Spring Boot application typically looks like:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Here, the **Java main** method calls `SpringApplication.run(...)` to initialize the `ApplicationContext`. The `@SpringBootApplication` annotation combines features such as auto-configuration and component scanning; it **does not generate a main method automatically**. Simply putting `@SpringBootApplication` on a class without a `main` method does not make it a valid entry point for standard packaging configuration.

### 2.3. `Main-Class` and `Start-Class` in the Manifest

When Spring Boot packages an **executable JAR** using the standard JAR layout, `META-INF/MANIFEST.MF` typically contains two key entries:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

This is a **typical Spring Boot 3.3 manifest excerpt**, not the complete manifest. Launcher locations and names can vary across versions/layouts.

- **`Main-Class`**: the class the JVM calls first when executing `java -jar app.jar`. In a normal Spring Boot executable JAR, this is the **Boot launcher**. The launcher sets up the classloader to locate dependency JARs nested inside the archive.
- **`Start-Class`**: the application class you wrote, containing the main method that the launcher calls after setting up the classpath.
- **`BOOT-INF/classes/`**: contains compiled classes and resources of the application.
- **`BOOT-INF/lib/`**: contains dependency JARs nested inside the executable archive.

Therefore, **do not confuse "choosing the application's main class" with "changing manifest `Main-Class` to your own class"**. If you overwrite `Main-Class` in a Spring Boot fat JAR to `com.example.demo.DemoApplication` via the Maven JAR Plugin or Gradle Jar manifest, you bypass the launcher required to load nested dependencies. With Spring Boot plugins, what you configure is normally **`mainClass` / `Start-Class`**, not arbitrarily overriding the launcher.

## 3. How Does Spring Boot Auto-Detect the Main Class?

The **starting point for auto-detection** is compiled classes in the application's **main source set**:

- **Gradle `bootJar` and `bootRun`**: the Spring Boot Gradle plugin can scan for classes with `public static void main(String[])` in the main source set output. If a suitable candidate is found, it sets that candidate as the task's main class.
- **Maven `spring-boot:repackage` / `spring-boot:run`**: the Spring Boot Maven plugin searches compiled classes for a main method. Candidate prioritization and handling of multiple classes can differ across plugin versions; modern documentation notes prioritizing classes annotated with `@SpringBootApplication` when applicable. Even so, **you should not rely on implicit selection behavior when multiple candidates exist**.
- **Classes in `src/test/java`** are not entry-point sources for a typical application executable JAR because test classes are outside the main output used for `repackage`/`bootJar`. A main method in the test suite does not necessarily cause a conflict; verify your build's actual source and directory configuration.

### When Is Auto-Detection Usually Fine?

When a project has **one clear main class**, auto-detection is simple and reduces configuration:

~~~text
src/main/java/com/example/demo/DemoApplication.java
    └── public static void main(String[] args)
~~~

Run `package` (Maven) or `bootJar` (Gradle), then check `Start-Class` in the archive. That remains a necessary verification step before release.

### When Is Auto-Detection No Longer Safe?

- There are **two or more classes** in the main output that each have a main method.
- A main method exists in a CLI utility class added later, or the application is split into **API + batch**.
- A `@SpringBootApplication` class was moved or renamed to another package while an older configured main class still points to the old name.
- A multi-module build accidentally pulls multiple module outputs onto the packaging task's classpath.
- Maven and Gradle plugins or different versions have **non-identical main-class lookup rules**.

Some plugins/builds fail complaining of an ambiguous main class, while others may pick an unintended candidate. **Do not treat class scan order, file order, or a local build "happening to work" as a stable contract.** Whenever two or more entry points exist, specify the **fully qualified class name (FQCN)** explicitly and verify the artifact.

## 4. Hands-On Example with Two Independent Entry Points

To see this clearly, create a Spring Boot project named `entrypoint-demo` with **two application classes in two separate packages**:

~~~text
entrypoint-demo/
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    ├── store/
                    │   └── StoreApplication.java
                    └── batch/
                        └── BatchApplication.java
~~~

The two packages `com.example.store` and `com.example.batch` are separate branches, giving each `@SpringBootApplication` its own **default component-scan scope**. The example only uses `spring-boot-starter`, starting no HTTP server, database, or scheduler. That ensures entry-point verification does not depend on external services.

### 4.1. File `src/main/java/com/example/store/StoreApplication.java`

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        System.out.println("ENTRY=STORE");
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

### 4.2. File `src/main/java/com/example/batch/BatchApplication.java`

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        System.out.println("ENTRY=BATCH");
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

Both classes have valid main methods and both are Spring Boot applications. **Multiple candidates are intentional** to highlight selecting the startup class during packaging. The goal of this example is not to run both applications simultaneously inside a single JVM.

The strings **`ENTRY=STORE`** and **`ENTRY=BATCH`** are exact markers printed by the Java code. Afterward Spring Boot may print a banner/startup logs with varying timestamps, PIDs, and versions; **do not treat the full log as fixed stdout**.

In real deployments, **Store** and **Batch** typically have separate lifecycles; if both are independent applications to be released, separate modules/artifacts are usually preferable to custom-packaging one shared JAR.

## 5. Maven Spring Boot Plugin: When There Is Only One Entry Point

### 5.1. A Buildable Base `pom.xml`

Use the following POM for the example in Section 4; this is a **complete POM**, assuming the repository has the Maven Wrapper `mvnw` / `mvnw.cmd` and JDK 17:

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
    <artifactId>entrypoint-demo</artifactId>
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

If there were only **one** main class in `src/main/java`, `spring-boot-maven-plugin` would usually locate it for packaging. Because Section 4 has **two** main classes, use the explicit approach in the next section instead of relying on auto-detection.

**Why don't we need to declare the `repackage` goal?** In a project inheriting from `spring-boot-starter-parent`, the `repackage` execution is already preconfigured by the parent and activates once `spring-boot-maven-plugin` is declared. If a project **does not inherit from the parent**, check the explicit execution configuration in Section 7.

**Packaging:** `./mvnw clean package` builds the archive from compiled classes and dependencies. Before `repackage`, the Maven JAR Plugin builds a standard JAR; `repackage` produces the **Spring Boot executable JAR** with the launcher, classpath layout, and `Start-Class`.

## 6. Maven with Spring Boot Starter Parent: Using `start-class`

In `pom.xml` from Section 5, add **one property** inside the existing `<properties>` block:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>com.example.store.StoreApplication</start-class>
</properties>
~~~

This is a **replacement snippet for the `<properties>` section in Section 5's POM**, not a standalone `pom.xml` file. `spring-boot-starter-parent` feeds the `start-class` property into the Spring Boot Maven plugin configuration per parent conventions, ensuring goals needing a main class know exactly which class to run.

### Building and Running the Store Variant

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean package
java -jar target/entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean package
java -jar .\target\entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

**Verifiable output:** the application output will contain the line:

~~~text
ENTRY=STORE
~~~

Alongside this line there will be the Spring Boot banner/logs (which are not fixed). Because the example uses only the base starter, the application completes startup and exits instead of listening on an HTTP port; that is not a launcher error.

### Switching to the Batch Variant

Simply change the property:

~~~xml
<start-class>com.example.batch.BatchApplication</start-class>
~~~

Re-run `clean package` and `java -jar` on the same JAR name. This time the exact marker is:

~~~text
ENTRY=BATCH
~~~

**Important:** the two builds produced **two artifacts with different contents under the exact same file name** `entrypoint-demo-0.0.1-SNAPSHOT.jar`. This is a learning exercise; **do not alternate publishing both artifacts under the same Maven coordinates/version as if they were identical**. If both Store and Batch must be deployed independently, choose separate modules or classifiers/artifact IDs along with a clear release process.

### When a Maven Project Has Multiple Entry Points

Without setting `start-class`, the Maven plugin may choose an undesired main class or fail unable to determine a candidate depending on version/configuration. **Explicit selection** by FQCN keeps a stable startup point across terminal, IDE, CI, and runtime.

If a main class is moved to another package while the property still points to the old class, `repackage` or running the executable JAR can fail. Verify the **post-compile FQCN**, not just the file name in your IDE.

## 7. Maven Without Inheriting the Starter Parent: Using the Plugin's `mainClass`

A project with a corporate parent or that only imports the `spring-boot-dependencies` BOM usually **does not inherit all plugin management and executions from `spring-boot-starter-parent`**. In that situation, configure the main class and `repackage` execution **directly on the Spring Boot Maven Plugin**.

The snippet below belongs inside `<build><plugins>` of a POM that already sets up its own dependencies/JDK/packaging:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <mainClass>com.example.store.StoreApplication</mainClass>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

**This is an XML fragment**, not a standalone POM. Make sure it goes inside `<build><plugins>`, and do not put `mainClass` configuration inside `maven-jar-plugin`. If the project uses the Starter Parent and already declares the plugin as in Section 5, **do not add a duplicate plugin block**; choose one consistent configuration strategy.

`mainClass` directly configures the Spring Boot Maven Plugin and controls the startup class used by the plugin. `repackage` runs after Maven creates the source JAR in `package`; calling `./mvnw spring-boot:repackage` alone in a workspace without a source JAR can fail. For a full build, run `./mvnw clean package` (when the execution is bound to the lifecycle), or follow plugin docs when invoking the goal after the `package` phase.

When only importing the BOM, the BOM **mainly manages dependency versions** and does not tell Maven to repackage or choose a main class. This is a key boundary between **dependency management** and **build plugin configuration**.

## 8. Gradle Spring Boot Plugin: Choosing the Main Class for an Executable JAR

### 8.1. A Buildable Groovy DSL Example

Using the same two Java files from Section 4, choose Gradle instead of Maven. `settings.gradle`:

~~~groovy
rootProject.name = 'entrypoint-demo'
~~~

`build.gradle`:

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
}

springBoot {
    mainClass = 'com.example.store.StoreApplication'
}
~~~

Gradle's `java` plugin creates the main source set; the Spring Boot plugin adds `bootJar` and `bootRun` tasks; `io.spring.dependency-management` works with the Spring Boot plugin to manage dependency versions via the corresponding BOM. `springBoot.mainClass` is a **project-level** setting applying a consistent main class across Boot tasks.

**When there is only one main class**, you can omit the `springBoot { mainClass = ... }` block and let Gradle auto-detect it. **When there are two classes**, keep the explicit block as shown above.

`repositories { mavenCentral() }` at the project level is valid for sample builds without `FAIL_ON_PROJECT_REPOS`. If a real project centralizes repositories in `settings`, follow the existing policy and **do not** add project-level repositories against rules.

### 8.2. Equivalent Kotlin DSL

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "entrypoint-demo"
~~~

`build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.store.StoreApplication")
}
~~~

This is an **alternative** to Groovy DSL; do not place both `settings.gradle` and `settings.gradle.kts` in the same directory. The Java files remain identical to Section 4.

### 8.3. Using the `bootJar` Property to Change Only the Archive

If you want to configure **only the packaging task** rather than the whole project, in Groovy DSL `build.gradle`:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.store.StoreApplication'
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.store.StoreApplication")
}
~~~

These snippets **replace** the `springBoot.mainClass` block in the example; do not combine both with conflicting values. In Kotlin, place the `import` at the top of the build file.

**Scope distinction:** setting `bootJar.mainClass` directly guarantees the `bootJar` task knows its entry point. It **does not automatically** make `bootRun` or IDE run configurations pick the same class. To keep both packaging and local execution aligned, use **project-wide `springBoot.mainClass`**, or configure both tasks explicitly and verify.

### 8.4. Configuring `bootRun` for Development

If you only want to run a specific entry point without building a JAR, Gradle uses `bootRun`.

Groovy DSL:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.batch.BatchApplication'
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.batch.BatchApplication")
}
~~~

**This snippet only controls `bootRun`.** It does not force `bootJar` to change its main class. Before handing off an artifact to CI/production, double-check your intent: if `bootRun` runs Batch while `bootJar` still packages Store, "works in IDE/dev, runs the wrong app from the JAR" is the natural result of two differing configs.

You can also use `application.mainClass` when a project additionally applies the Gradle Application plugin. However, for a standard Spring Boot app, **there is no need to add the Application plugin just to select a main class**: `springBoot.mainClass` is already clearer.

## 9. Running Gradle on Windows and Linux and Verifying the Entry Point

In a project with the Gradle Wrapper and the configuration from Section 8:

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean bootJar
./gradlew bootRun
java -jar build/libs/entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean bootJar
.\gradlew.bat bootRun
java -jar .\build\libs\entrypoint-demo-0.0.1-SNAPSHOT.jar
~~~

When `springBoot.mainClass = com.example.store.StoreApplication` is set, both `bootRun` and `java -jar` must invoke the Store application. The expected marker line in both runs is:

~~~text
ENTRY=STORE
~~~

Switch `springBoot.mainClass` to `com.example.batch.BatchApplication`, rebuild, and run the JAR:

~~~text
ENTRY=BATCH
~~~

**Do not skip `clean bootJar` when testing entry-point changes:** it prevents accidentally running a stale artifact. In normal builds Gradle uses incremental/cache optimizations, but when verifying main class configuration, you want certainty about which build produced the JAR you are running.

The Spring Boot Gradle plugin can also produce a **plain JAR** when the `jar` task remains enabled; in certain configs the file carries the `-plain` classifier. Do not run `entrypoint-demo-...-plain.jar` by mistake and conclude the Boot launcher is broken: a plain JAR may lack nested dependencies and a manifest suited for `java -jar`.

## 10. Inspecting `Start-Class` in the Artifact Instead of Guessing from Logs

A reliable check is opening the manifest of **the exact executable JAR created by the latest build**:

~~~text
META-INF/MANIFEST.MF
~~~

In either the Maven or Gradle example, the two key attributes are:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.store.StoreApplication
~~~

If configured for Batch, the second line must become:

~~~text
Start-Class: com.example.batch.BatchApplication
~~~

### 10.1. Linux/macOS: Viewing the Manifest Without Extracting the Whole JAR

Assuming `unzip` is available:

~~~bash
# Maven, after running ./mvnw clean package
unzip -p target/entrypoint-demo-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF

# Gradle, after running ./gradlew clean bootJar
unzip -p build/libs/entrypoint-demo-0.0.1-SNAPSHOT.jar \
  META-INF/MANIFEST.MF
~~~

The output may include additional attributes and line wraps per manifest rules. Look specifically for `Main-Class` and `Start-Class` rather than treating the excerpt above as the entire file.

If `unzip` is not installed, the JDK's `jar` tool can list entries and extract the manifest into a **separate inspection directory**. There is no need to edit the manifest manually.

### 10.2. Windows PowerShell: Using the JDK `jar` Tool

After building, an inspection method **without needing `unzip`**:

~~~powershell
# Maven: prepare a separate directory so project files are not overwritten
New-Item -ItemType Directory -Force .\manifest-check | Out-Null
Push-Location .\manifest-check
jar xf ..\target\entrypoint-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
Pop-Location
~~~

If using Gradle, replace the path in `jar xf` with:

~~~powershell
jar xf ..\build\libs\entrypoint-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
~~~

This Gradle alternative also runs **after entering** `manifest-check`. If PowerShell is still at the project root, `..\build` is wrong: make sure you are in the right working directory. Use `Get-ChildItem .\target\*.jar` (Maven) or `Get-ChildItem .\build\libs\*.jar` (Gradle) if your actual JAR name differs from the example.

### 10.3. Verifying the Nested JAR Structure

Linux/macOS:

~~~bash
jar tf target/entrypoint-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/'
~~~

For Gradle use `build/libs/...`. If classes sit only at the root and there is no `BOOT-INF/classes` or `BOOT-INF/lib`, you may be inspecting a **plain JAR**, `repackage`/`bootJar` did not run, or a different layout/packaging was chosen. Do not edit `Start-Class` to fix an archive that lacks the right loader and dependencies.

**The manifest is build-artifact evidence**, not proof that the application will initialize successfully: it can still fail due to config, database, or Java runtime issues at startup. Thus, **checking the manifest and running `java -jar`** are complementary steps.

## 11. Selecting a Main Class via Build Profiles or Variants

Some teams need to test two entry points from the same codebase. You can configure an **intentional build variant**, provided you avoid distributing two different artifacts under the same release coordinates.

### 11.1. Maven Profiles with the Starter Parent

If the project uses the `start-class` property with the Parent, you can **move the choice into profiles**:

~~~xml
<profiles>
    <profile>
        <id>store</id>
        <properties>
            <start-class>com.example.store.StoreApplication</start-class>
        </properties>
    </profile>
    <profile>
        <id>batch</id>
        <properties>
            <start-class>com.example.batch.BatchApplication</start-class>
        </properties>
    </profile>
</profiles>
~~~

This is a **fragment placed under `<project>`**, not a standalone POM. If applied, remove the fixed `start-class` property from Section 6 or define an explicit fallback. Run:

~~~bash
./mvnw -Pstore clean package
# or:
./mvnw -Pbatch clean package
~~~

After each run, inspect `Start-Class` to confirm the profile actually took effect. Do not activate `-Pstore,batch` simultaneously because both modify the same property, creating hard-to-control conflicts. **The default JAR name can remain identical** across builds. If both must be released, create separate modules/artifacts or configure explicit classifiers and an official release process.

### 11.2. Gradle Property to Pick a Variant at Build Time

In Groovy DSL, you can drive the main class from a Gradle project property:

~~~groovy
springBoot {
    mainClass = providers.gradleProperty('appMain')
        .orElse('com.example.store.StoreApplication')
}
~~~

This is an **alternative** to a fixed `springBoot.mainClass`. Run:

~~~bash
./gradlew clean bootJar
./gradlew clean bootJar -PappMain=com.example.batch.BatchApplication
~~~

The first command defaults to Store, while the second chooses Batch. **The Gradle project property `appMain` is not a Spring runtime property**; it is evaluated at Gradle configuration time. When using this option in CI, pass `-PappMain=...` explicitly in the pipeline, log the selected value, and inspect the manifest. Do not let an uncontrolled property silently alter the entry point of a release artifact.

Equivalent Kotlin DSL:

~~~kotlin
springBoot {
    mainClass.set(
        providers.gradleProperty("appMain")
            .orElse("com.example.store.StoreApplication")
    )
}
~~~

**Technical note:** if the project also configures `bootJar.mainClass` or `bootRun.mainClass` with a different value, check which setting each task actually uses. Avoid combining multiple ways of controlling the same property without a clear reason and tests.

## 12. One JAR with Two Entry Points or Two Separate JARs?

Having **two classes with main methods** does not mean a standard executable JAR will run both in sequence. In the basic Spring Boot executable JAR layout, one manifest carries only **one `Start-Class`** selected for default `java -jar` execution.

| Requirement | Suitable Design | Things to Note |
| --- | --- | --- |
| One Spring Boot service; the other main is only a dev tool | Explicitly set the service's main via build config | Do not let a CLI utility accidentally become the entry point |
| Trying Store or Batch via build commands | Use properties/profiles as in Section 11 on an experimental branch | Re-read the manifest after **every** build; avoid stale JARs |
| Store and Batch are two independently deployed apps | **Multi-module** or two separate projects/artifacts, each with one entry point | Independent versioning, CI, Docker images, config, and runtime |
| Two artifacts packaged from shared sources with different startups | Multiple packaging tasks with distinct classifiers/names when carefully designed | Never reuse the same file name and Maven GAV for two different contents |
| Selecting a class at runtime via `java -cp app.jar ...` | Do not use this directly with a default Spring Boot nested JAR | Nested dependencies are not read by a standard Java classpath like a flat JAR |

**Suggested multi-module layout:**

~~~text
root/
├── shared-core/              # shared code, no executable main needed
├── store-app/                # StoreApplication, builds Store executable JAR
└── batch-app/                # BatchApplication, builds Batch executable JAR
~~~

Each app module has the appropriate packaging plugin, dependencies, and artifact name. `shared-core` uses an ordinary library plugin since it does not need the Boot launcher. Auto-detection within each app module becomes simpler because each module has one clear entry point.

Advanced launchers/layouts such as `PropertiesLauncher` and `loader.main` exist, yet that is **no** reason to overwrite manifests casually or assume `java -cp` works with nested JARs. When deploying two real applications, **separate artifacts are much easier to understand, test, and operate**.

## 13. Correctly Understanding `bootRun`, Maven `spring-boot:run`, and `java -jar`

| Execution Method | Classpath Source | Entry Point Used |
| --- | --- | --- |
| `./gradlew bootRun` | Main source set output + Gradle runtime classpath | `bootRun.mainClass`, project-wide Spring Boot config, or auto-detection |
| `./mvnw spring-boot:run` | Compiled classes + dependencies from Maven model | Spring Boot Maven plugin config or auto-detection |
| `java -jar target/app.jar` | Contents of Maven `repackage`d executable archive | `Main-Class` launcher → `Start-Class` recorded in manifest |
| `java -jar build/libs/app.jar` | Contents of Gradle `bootJar` executable archive | `Main-Class` launcher → `Start-Class` recorded in manifest |

`bootRun` and `spring-boot:run` run the application **in-place**, without requiring a JAR to be built first. Conversely, `java -jar` reads the packaged archive; changing source code or build config after the JAR was built **does not automatically update** an existing JAR's manifest.

If the IDE runs Store yet the deployed JAR runs Batch, check:

1. Which main class is selected in the IDE Run Configuration?
2. Does `bootRun` / `spring-boot:run` specify its own `mainClass`?
3. Which JAR did the build just produce, from which module, with what classifier/version?
4. Which `Start-Class` appears in the manifest of **the exact JAR file being deployed**?

**Do not** try to fix this mismatch merely by toggling `spring.profiles.active`: Spring runtime profiles select configurations/beans **after** a main class has already been invoked. They do not change the entry point recorded in the manifest.

## 14. Common Errors and Fixing Them at the Right Layer

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Gradle fails unable to determine `bootJar` main class | No main method in main output or multiple candidates | Check `src/main/java`, package, compile output; set `springBoot.mainClass` or `bootJar.mainClass` |
| Maven `repackage` cannot find main class | Plugin cannot pick a candidate, class uncompiled, or wrong package/classname | Specify `start-class` (with Parent) or `<mainClass>` on Spring Boot Maven Plugin |
| Maven/Gradle reports "build succeeded" yet JAR runs the wrong program | Auto-detection/wrong variant selected or stale archive executed | Check manifest `Start-Class` and `ENTRY=...` marker, verify path/module |
| `ClassNotFoundException` / `Could not find or load main class` | Wrong FQCN in config, class moved packages, output missing class | Compare package/file/bytecode names against `Start-Class`, clean rebuild |
| `no main manifest attribute` | Running plain JAR or `repackage` did not execute | Maven: check `spring-boot-maven-plugin` + `repackage` goal; Gradle: run `bootJar` |
| `NoClassDefFoundError` or Spring class missing at runtime | Running plain JAR without nested libraries or corrupted archive | Run the proper Boot executable JAR, check `BOOT-INF/lib`, do not manually edit launcher manifest |
| `Main-Class` shows `JarLauncher` instead of `StoreApplication` | This is the **correct** behavior for a Spring Boot executable JAR | Read `Start-Class` next; do not replace the launcher with app main |
| `UnsupportedClassVersionError` at runtime | Runtime JDK is older than compiled class/dependency bytecode | Compare `java -version`, compiler toolchain, and Java target |
| IDE runs Store yet `java -jar` runs Batch | IDE run config or `bootRun` differs from packaging config, or stale JAR | Compare task-level vs. project-wide `mainClass`, manifest, and build timestamp |
| One module picks the right main, another picks wrong | Multi-module build has inconsistent plugins/configurations | Check `mainClass` and outputs per module, use `:module:bootJar` or `-pl` |
| App prints a few logs then exits | Project only includes `spring-boot-starter`, no web server or long-running job | This can be normal; check exceptions and exit code before blaming main |
| Enabled `spring.profiles.active=batch` yet Store still runs | Spring profile is runtime config, not the Java entry point | Choose the right `Start-Class`/`mainClass` at build time |
| Set `<start-class>` in Maven with no effect | Project does not inherit `spring-boot-starter-parent` or another plugin config overrides it | Inspect effective POM; use `<mainClass>` inside Spring Boot Plugin per project setup |
| WAR package or `NONE` layout has a different manifest from sample | Packaging layout differs from standard executable JAR | Read plugin/format config; do not force conclusions from `JarLauncher` samples |
| Store and Batch JARs share the same filename/version | Variant builds overwrote the archive at the same coordinates | Use distinct names/classifiers/modules or separate release workflows |

**Do not try to fix entry-point selection bugs by wiping caches wholesale or randomly bumping framework versions.** First record **the build command, plugin version, source classpath, `mainClass` config, artifact name, `Main-Class`, `Start-Class`, and exact run command**.

## 15. Checking Main Class in CI and Ensuring the Right Artifact

CI should use a **project-controlled JDK and Wrapper**, rather than relying on an entry point guessed by an IDE. A proper job should:

- Run Maven `clean package` or Gradle `clean bootJar` on the right module.
- Select **one single artifact** to deploy instead of picking the first JAR in a directory that might also hold `-plain.jar`, `.original`, or stale builds.
- Read the manifest and assert `Start-Class` matches the expected application FQCN.
- Run an appropriate smoke test (`java -jar` with supplied runtime/config), checking the marker or health endpoint provided by the application itself.
- Store artifacts under unambiguous names/versions so two variants cannot be confused; builds from the same commit using different profiles/properties must be tracked.
- If the project deploys multiple programs, **split pipelines/artifacts by module** instead of creating a "fat JAR" whose behavior silently mutates.

Example manifest check snippet for Linux CI with `unzip`, after a Maven build:

~~~bash
jar_path="target/entrypoint-demo-0.0.1-SNAPSHOT.jar"
unzip -p "$jar_path" META-INF/MANIFEST.MF |
  grep -F 'Start-Class: com.example.store.StoreApplication'
~~~

This command checks that **the manifest contains the expected line**; it does not run the application. In a Linux shell with `set -o pipefail` or a CI shell with proper fail-on-error handling, a failed match keeps the job from succeeding. If `unzip` is not installed, use the JDK's `jar` tool to extract the manifest into a temporary directory and inspect its contents.

**Remember to test runtime behavior:** a valid manifest does not guarantee the app runs inside the server image. Java target, dependencies, Spring configuration, and external service access must be tested in the pipeline or an appropriate integration environment.

## 16. Hands-On Exercise with Acceptance Criteria

Using **either** Maven or Gradle on an experimental branch of a Spring Boot project:

1. Create `StoreApplication.java` and `BatchApplication.java` as in Section 4, ensuring each class has `public static void main(String[] args)` and prints a distinct marker.
2. Choose the Maven POM from Section 5 or the Gradle build from Section 8; **do not keep both Maven and Gradle in the same project**.
3. First try building without declaring a main class: observe the output and note whether your current plugin version picks one automatically or reports ambiguity. **Do not rely on that incidental outcome as release config.**
4. Explicitly select Store via `<start-class>` (Maven Parent) or `springBoot.mainClass` (Gradle).
5. Run `clean package` / `clean bootJar`, then read `Start-Class` in the manifest. Verify it equals `com.example.store.StoreApplication`.
6. Run `java -jar` on the **exact JAR** just built and observe the `ENTRY=STORE` marker.
7. Switch to Batch, rebuild, and verify `Start-Class` + the `ENTRY=BATCH` marker.
8. If using Gradle, intentionally configure `bootRun` and `bootJar` with different entry points: compare results and explain why the two commands behave differently. Then restore consistent configuration.
9. Record your design decision: are these merely **two learning variants**, or **two applications needing independent artifacts**? If the latter, propose splitting modules/artifacts.
10. Restore the project's standard config/main class, re-run builds/tests, and confirm CI can read the manifest.

**You have completed this lesson when** you can answer accurately: when does the plugin auto-detect main; where to declare it when multiple mains exist; how `Main-Class` differs from `Start-Class`; why `java -jar` can behave differently from an IDE; and how to prove **the right entry point lives inside the exact artifact being deployed**.

## Official Documentation

- [Spring Boot Maven Plugin – Using the Plugin / Specifying Main Class](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot Maven Plugin – Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Maven Plugin – Repackage Goal](https://docs.spring.io/spring-boot/maven-plugin/repackage.html)
- [Spring Boot Gradle Plugin – Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Gradle Plugin – Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot – Executable JAR Specification, Launching](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
- [Apache Maven – Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Gradle – Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)