# Troubleshooting Missing Main Class or Multiple Main Classes in Spring Boot

## 1. Goal and Approach

Under the **Troubleshooting** topic group, this lesson addresses two common errors when packaging Spring Boot applications:

1. The build cannot find a main class, fails to resolve an entry point, or creates an archive that cannot run with `java -jar`.
2. The project contains multiple classes with `public static void main(String[] args)`, causing the build tool to pick the wrong startup class or fail to determine the team's intended choice.

With Java 17, the standard entry point is the **public static void main(String[] args)** method. A Spring Boot executable JAR adds its own launcher layer, so you must distinguish:

- **Application main class:** the class written by the development team containing the main method.
- **`Main-Class` in the Boot JAR manifest:** the Spring Boot launcher class responsible for setting up the classloader and loading nested JARs.
- **`Start-Class` in the manifest:** the FQCN of the application main class that the launcher will invoke.

When there are multiple candidates, the reliable solution is to explicitly configure the **fully qualified class name (FQCN)** in the Spring Boot Maven Plugin or Gradle Plugin. When there are no candidates, check the source set, method signature, package, module, and compiled output before editing the manifest.

This lesson uses **Java 17, Spring Boot 3.3.5, Maven 3.9.x, or Gradle 8.5**. The examples use a fixed version set for practice; when applying to a project, use versions tested by your organization.

## 2. Main Class in Java 17

### 2.1. Standard Entry Point Signature

The Java launcher looks for a matching main method in the class requested to run. For Java 17, the clear and standard form is:

~~~java
public static void main(String[] args)
~~~

Meaning:

- **public:** the launcher can invoke the method from outside the class.
- **static:** no object instance needs to be created before invoking it.
- **void:** returns no value to the launcher.
- **main:** the recognized method name.
- **String[] args:** the command-line arguments array.

The varargs form is equivalent in signature:

~~~java
public static void main(String... args)
~~~

The forms below are not standard Java 17 entry points:

~~~java
private static void main(String[] args) { }
public void main(String[] args) { }
public static int main(String[] args) { return 0; }
public static void main() { }
public static void Main(String[] args) { }
~~~

The method name is case-sensitive. Java 17 requires the traditional static main form; do not apply preview features or entry point declarations from newer JDKs to a project targeting 17.

### 2.2. Annotations Do Not Replace the Main Method

The **@SpringBootApplication** annotation marks application configuration and enables auto-configuration and component scanning. This annotation does not generate a main method on its own.

For example, the following class is valid Java syntax yet lacks an entry point for packaging as an executable Boot JAR:

~~~java
package com.example.catalog;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
}
~~~

If you want the archive to run via `java -jar`, add a main method and call `SpringApplication.run`.

### 2.3. The Main Class Must Reside in the Main Source Set

Standard structure:

~~~text
src/
├── main/
│   └── java/
│       └── com/example/catalog/CatalogApplication.java
└── test/
    └── java/
        └── com/example/catalog/CatalogApplicationTests.java
~~~

Maven compiles application code from **src/main/java**. The Gradle Java plugin uses the **main source set**. A class located only under `src/test/java` is not a main class for the executable application archive.

Check these cases:

- Main class mistakenly placed in the test source set.
- Generated sources not yet attached to the compile task or main source set.
- Spring Boot plugin mistakenly applied to a `core` module instead of `app`.
- Source file declares a different package than the configured FQCN.
- Mismatch in class name, package, or letter casing.
- Build is running in a subproject that does not contain the class to be packaged.

### 2.4. Configuring by FQCN

Example:

~~~java
package com.example.catalog;

public class CatalogApplication {
    public static void main(String[] args) {
        System.out.println("CATALOG_APP_STARTED");
    }
}
~~~

Exact FQCN:

~~~text
com.example.catalog.CatalogApplication
~~~

Do not use a filename, filesystem path, or `.java`/`.class` extension. Main class configuration takes the fully qualified Java name, not a source path.

## 3. Distinguishing the Two Error Scenarios

| Scenario | Common Symptoms | Where to Check First |
| --- | --- | --- |
| No main class | Plugin cannot find main class; Gradle cannot resolve entry point; repackage/bootJar fails | Source set, method signature, module, compile output |
| Multiple main classes | Build picks the wrong application or auto-detection yields an unintended class | FQCN and `mainClass` configuration |
| Configured name is right, class missing | Archive may be built, yet `java -jar` cannot load `Start-Class` | Package name, class output, module, artifact |
| Wrong manifest | `no main manifest attribute` or wrong launcher | `META-INF/MANIFEST.MF` and plugin configuration |
| Running the wrong file | Plain JAR lacks Boot layout | `target`/`build/libs` paths and classifier |

Error messages can vary by plugin version, lifecycle, and task. Inspect the failing goal/task, module, and archive path instead of relying solely on an error line copied from another project.

## 4. `Main-Class` and `Start-Class` in a Spring Boot JAR

A regular Java JAR can place the application class in the manifest's `Main-Class` attribute. A Spring Boot executable JAR needs a launcher to load dependencies nested inside the archive.

Typical Spring Boot 3.3 manifest:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
~~~

The two attributes serve different roles:

- **Main-Class** points to the Boot Launcher. The launcher sets up the classloader and finds classes/resources in nested JARs.
- **Start-Class** points to the application's main class containing `public static void main(String[])`.

Therefore, when using the Spring Boot Maven/Gradle Plugin, do not arbitrarily set `Main-Class` to the application class. Configure the main class in the Spring Boot plugin; the plugin manages the manifest according to the archive layout.

For an executable WAR, the launcher is typically `WarLauncher`; for an executable JAR, the launcher is `JarLauncher`. Launcher package/class names can depend on the Spring Boot version, so inspect the manifest of the actual built artifact.

## 5. Java 17 Example with Two Main Classes

### 5.1. Application Main Class

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

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
    CommandLineRunner startupProof() {
        return args -> System.out.println("CATALOG_APP_STARTED");
    }
}
~~~

This is the Spring Boot application entry point. The example uses the basic starter and opens no HTTP server. When the context starts and `CommandLineRunner` runs, the code prints `CATALOG_APP_STARTED`.

### 5.2. Second Main Class

File **src/main/java/com/example/catalog/tools/MigrationTool.java**:

~~~java
package com.example.catalog.tools;

public class MigrationTool {

    public static void main(String[] args) {
        System.out.println("MIGRATION_TOOL_STARTED");
    }
}
~~~

Both classes have valid main methods. This is not necessarily a bug: they can represent two entry points with different purposes.

However, a specific executable Boot JAR has one selected `Start-Class`. Maven and Gradle have different auto-detection mechanisms; do not rely on file scan order to decide which application runs.

### 5.3. Expected Result

If the archive is configured for `CatalogApplication`, running:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

must start `CatalogApplication` and the log must contain the line:

~~~text
CATALOG_APP_STARTED
~~~

It must not start `MigrationTool` merely because that class also contains `main`.

If both the application and the migration tool need to be released as two independent programs, consider splitting them into two modules/artifacts. Each artifact gets its own manifest, dependency graph, runtime configuration, and release contract.

## 6. Maven: Configuring the Main Class Explicitly

### 6.1. Configuring the Spring Boot Maven Plugin

In the application module's POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.catalog.CatalogApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The FQCN must point to a class in the app module's compiled output.

If the POM inherits **spring-boot-starter-parent**, the `repackage` goal is already configured in the lifecycle with execution ID `repackage`. In the standard case, just declare the plugin and configure `mainClass` as shown above.

If **not** using the Spring Boot starter parent, bind the `repackage` goal yourself:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.catalog.CatalogApplication</mainClass>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Do not add a duplicate execution when the parent already defines the `repackage` execution. If overriding inherited configuration, use the parent's exact execution ID.

### 6.2. Complete POM for the Maven Application

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
    <artifactId>catalog-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <configuration>
                    <mainClass>com.example.catalog.CatalogApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This POM configures Java 17, Spring Boot 3.3.5, the basic starter, `starter-test`, and an explicit main class for `repackage`.

### 6.3. Build and Run with Maven

~~~bash
./mvnw -B -ntp clean package
~~~

Default artifact:

~~~text
target/catalog-app-1.0.0.jar
~~~

Run:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

If the project uses a custom classifier or `finalName`, use the actual artifact path.

### 6.4. Maven Multi-Module: Placing the Plugin in the Right Module

Example:

~~~text
catalog-platform/
├── pom.xml
├── catalog-core/
│   └── pom.xml
└── catalog-app/
    └── pom.xml
~~~

The root POM usually has `pom` packaging and declares `<modules>`. `catalog-core` is a Java library; `catalog-app` is the executable application.

**Spring Boot Maven Plugin and the `mainClass` configuration should reside in `catalog-app/pom.xml`**, where `CatalogApplication` lives. Do not apply `repackage` to the root aggregator or core library merely because you want to build the whole reactor.

Build the app along with its dependent modules:

~~~bash
./mvnw -pl catalog-app -am clean package
~~~

If the app has multiple main classes, `mainClass` still points to the desired entry point. If `core` also contains a main class, do not inadvertently mix `core` into the app's Boot plugin configuration.

### 6.5. Specifying Main Class for `spring-boot:run`

When running the app via Maven before packaging:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.main-class=com.example.catalog.CatalogApplication
~~~

The property above applies to the `spring-boot:run` goal. To control `repackage`, configure `mainClass` in the Spring Boot Maven Plugin. Do not assume a property meant for the `run` goal automatically changes other executions.

## 7. Gradle: Configuring `mainClass` for `bootJar`

### 7.1. Spring Boot DSL Configuration

File **build.gradle** (Groovy DSL):

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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`springBoot.mainClass` is the project-level configuration for the application main class. The Spring Boot Gradle Plugin uses it to configure executable archives and `bootRun` according to the plugin's mechanism.

This is the right choice when a project has multiple main classes yet wants a single default entry point.

### 7.2. Configuring Directly on `bootJar`

You can configure the specific task:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

This makes it explicit which archive uses which main class. If a project has multiple executable archives/tasks, task-level configuration lets each archive use its own entry point.

Do not mistakenly configure the `jar` task. The `jar` task creates a plain JAR; the executable Spring Boot JAR is created by `bootJar`.

### 7.3. Kotlin DSL

With `build.gradle.kts`, project-level configuration:

~~~kotlin
springBoot {
    mainClass.set("com.example.catalog.CatalogApplication")
}
~~~

Or task-level:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    mainClass.set("com.example.catalog.CatalogApplication")
}
~~~

Kotlin DSL uses `Property<String>`, so `set()` is typically called. Do not copy Groovy DSL verbatim into Kotlin DSL.

### 7.4. Build and Run with Gradle

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Default artifact:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

Run:

~~~bash
java -jar build/libs/catalog-app-1.0.0.jar
~~~

If there are multiple main classes, verify that the manifest `Start-Class` matches the selected FQCN.

### 7.5. Configuring Main Class for `bootRun`

You can run the app directly via Gradle:

~~~bash
./gradlew bootRun
~~~

If separate task configuration is needed:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Or use `springBoot.mainClass` at the project level. `bootRun` runs from the main source set. Spring Boot Gradle Plugin also provides the `bootTestRun` task for the test source set; do not use a test main class as the entry point for a production `bootJar`.

## 8. Handling Projects with Multiple Main Classes

### 8.1. Do Not Rely on Auto-Detection Order

The Spring Boot Maven Plugin can use **the first compiled class found with a main method** if `mainClass` is not configured. Thus, adding a new migration or CLI class may cause auto-detection to pick a different class than the team intended to release.

Gradle `BootJar` scans for classes with `public static void main(String[])` in the main source set output. When multiple candidates exist, do not rely on auto-detection or file scan order; set `mainClass` explicitly.

Key points to remember:

- Maven and Gradle have different auto-detection mechanisms.
- A successful build does not prove the right entry point was chosen.
- A given executable archive has one `Start-Class`.
- If multiple independent applications are needed, create multiple artifacts/modules or separately configured packaging tasks.

### 8.2. Choosing One Canonical Main Class

Suppose the project contains:

~~~text
com.example.catalog.CatalogApplication
com.example.catalog.tools.MigrationTool
com.example.catalog.tools.ReindexTool
~~~

But the primary artifact is the Catalog API. Maven:

~~~xml
<configuration>
    <mainClass>com.example.catalog.CatalogApplication</mainClass>
</configuration>
~~~

Gradle:

~~~groovy
springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

`MigrationTool`/`ReindexTool` can still be invoked via separate tasks, tests, or another artifact; they will not become the entry point of the main Boot JAR.

### 8.3. When Multiple Independent Executables Are Needed

If the migration tool and web application have different lifecycles, dependencies, or runtime configurations, split modules:

~~~text
catalog-platform/
├── catalog-core/
├── catalog-api/
│   └── CatalogApplication.java
└── catalog-migration/
    └── MigrationApplication.java
~~~

Each app module has its own main class, plugin configuration, artifact name, runtime dependency graph, and deployment configuration. This is usually easier to operate than a single Boot JAR with multiple entry points.

### 8.4. Multiple `BootJar` Tasks in Gradle

You can create multiple executable archive tasks when there is a clear need. Each task needs the proper `mainClass`, classpath, archive classifier, output destination, and task dependencies. Do not merely register a `BootJar` task and assume the plugin configures every property identically to the default `bootJar` task.

Before creating multiple custom tasks, consider splitting modules. If staying within one module, inspect the manifests and test each archive to ensure each file starts the intended application.

## 9. Diagnosing When No Main Class Is Found

### Step 1: Identify the Right Module and Task

Maven:

~~~bash
./mvnw -pl catalog-app -am clean package
~~~

Gradle:

~~~bash
./gradlew :catalog-app:clean :catalog-app:bootJar
~~~

Verify that the plugin is applied to the module containing the application class, not the root aggregator or a library module.

### Step 2: Confirm the Source File Is in the Main Source Set

Maven:

~~~text
catalog-app/src/main/java/com/example/catalog/CatalogApplication.java
~~~

The Gradle Java plugin uses `src/main/java` by default. If the class is only in `src/test/java`, the plugin will not find it in main output.

### Step 3: Check the Method Signature

Look for the exact signature:

~~~java
public static void main(String[] args)
~~~

Check `public`, `static`, `void`, lowercase `main`, and parameter `String[]`. The method must live in a class with the right package and compile cleanly.

### Step 4: Check the Compiled Class

Maven:

~~~text
target/classes/com/example/catalog/CatalogApplication.class
~~~

Gradle:

~~~text
build/classes/java/main/com/example/catalog/CatalogApplication.class
~~~

If the file does not exist, resolve compilation, source set, or code generation issues before modifying plugin configuration.

### Step 5: Verify the FQCN

If the source declares `package com.example.catalog`, configure `com.example.catalog.CatalogApplication`. Do not leave an old package name after refactoring.

### Step 6: Configure `mainClass` Explicitly

In Maven, set `mainClass` in `spring-boot-maven-plugin`. In Gradle, set `springBoot.mainClass` or `bootJar.mainClass`. This is the primary fix when multiple candidates exist or auto-detection picks the wrong one.

### Step 7: Clean and Rebuild

Maven:

~~~bash
./mvnw -B -ntp clean package
~~~

Gradle:

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Cleaning removes stale outputs left behind after a class was renamed or deleted.

## 10. Diagnosing Multiple Main Classes

### 10.1. Search for `main` Methods in Source

Linux/macOS:

~~~bash
grep -R -n "static void main" src/main/java
~~~

PowerShell:

~~~powershell
Get-ChildItem src/main/java -Recurse -Filter *.java |
    Select-String -Pattern 'static void main'
~~~

This is a quick text search, not a Java parser. It can miss methods formatted across multiple lines or match comments/strings. Use the results to identify which classes to read and verify.

### 10.2. Check Compiled Class with `javap`

~~~bash
javap -classpath target/classes -public com.example.catalog.CatalogApplication
~~~

Expected output should include:

~~~text
public static void main(java.lang.String[]);
~~~

If `javap` reports class not found, check the classpath, output directory, and package name.

### 10.3. Do Not Confuse Test Main with App Main

A test utility may contain a `main` method, yet it should not be the production entry point.

- Maven Boot `repackage` uses the module's compiled application classes.
- Gradle `BootJar` searches the main source set.
- Gradle `bootTestRun` targets the test source set and does not replace `bootJar`.

If a test helper was mistakenly placed in `src/main/java`, move it to `src/test/java` if it is only for testing.

## 11. Inspecting Manifest and Archive Contents

### 11.1. List the JAR

Maven:

~~~bash
jar tf target/catalog-app-1.0.0.jar
~~~

Gradle:

~~~bash
jar tf build/libs/catalog-app-1.0.0.jar
~~~

A typical executable Boot JAR contains:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/...
~~~

If you only see classes at the package root and no `BOOT-INF`, you may be inspecting a plain JAR.

### 11.2. Read Manifest on Linux/macOS

~~~bash
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
~~~

With Spring Boot 3.3, typical manifest:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
~~~

If `Start-Class` points to an old class or a different class, the `mainClass` configuration was not applied or the inspected artifact is not the latest output.

### 11.3. Read Manifest on Windows PowerShell

~~~powershell
jar xf target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
~~~

`jar xf` extracts the manifest into the current working directory. Use a temporary directory or check beforehand to avoid overwriting existing files.

### 11.4. Run the Right Artifact

Maven:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

Gradle:

~~~bash
java -jar build/libs/catalog-app-1.0.0.jar
~~~

If using a custom classifier or `finalName`, substitute the actual path. Do not pick the first file by wildcard when a directory contains both a plain JAR and a Boot JAR.

## 12. Special Cases

### 12.1. Kotlin Top-Level `main`

With Kotlin:

~~~kotlin
fun main(args: Array<String>) {
    println("KOTLIN_APP_STARTED")
}
~~~

The compiler typically generates a Java class with a `Kt` suffix, for example:

~~~text
CatalogApplicationKt
~~~

The FQCN may be:

~~~text
com.example.catalog.CatalogApplicationKt
~~~

If `@file:JvmName` is used, the generated class name changes. Configure the JVM class name generated by the compiler; do not guess from the `.kt` filename alone.

### 12.2. Main Class from Generated Sources

An annotation processor or code generator may create the main class. Confirm that the generated directory is attached to the main compile source set and the class appears in compiled output before repackaging.

If the generated file is only created by a task not wired into `compileJava`, packaging can run without the expected class.

### 12.3. Core Module Also Contains a `main` Method

A library module may contain a demo/test `main`. Do not apply the Spring Boot plugin to `core` merely because it has a `main` method. `core` normally produces a plain JAR; the app module configures its own entry point.

### 12.4. Project Does Not Need an Executable Archive

If the deliverable is just a library, use Maven `jar` packaging or the Gradle Java/Java Library plugin. Spring Boot Maven Plugin has a `NONE` layout to bundle dependencies without a bootstrap loader, yet that archive **is not an executable JAR to run via `java -jar`**.

### 12.5. Class Has `main` Without Starting Spring

A class with a `main` method can be a valid Java entry point without necessarily starting a Spring context. If Spring Boot is required, the `main` method must initialize the application, e.g., `SpringApplication.run`. The existence of a `main` method does not prove Spring configuration is valid.

## 13. Java 17 Utility to Inspect the Main Method

Create **MainMethodInspector.java** in an independent tools directory:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class MainMethodInspector {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java MainMethodInspector.java <fully-qualified-class>");
            System.exit(2);
        }

        Class<?> type = Class.forName(args[0]);
        Method main = type.getMethod("main", String[].class);

        int modifiers = main.getModifiers();
        boolean valid = Modifier.isPublic(modifiers)
                && Modifier.isStatic(modifiers)
                && main.getReturnType() == void.class;

        if (!valid) {
            System.err.println("INVALID_MAIN_METHOD");
            System.exit(1);
        }

        System.out.println("MAIN_METHOD_OK:" + type.getName());
    }
}
~~~

This is a complete Java 17 source-file launcher program. It uses reflection to load the class by name and look up a method taking a `String[]` parameter.

Run after application classes have compiled:

~~~bash
java -cp target/classes MainMethodInspector.java com.example.catalog.CatalogApplication
~~~

On success, stdout:

~~~text
MAIN_METHOD_OK:com.example.catalog.CatalogApplication
~~~

If the class or method is not found, the program throws an exception. If the method exists with invalid modifiers/return type, stderr prints `INVALID_MAIN_METHOD` with exit code 1.

**Limitation:** this program only inspects method reflection on a compiled class. It does not verify `@SpringBootApplication`, the dependency graph, the manifest, or whether the whole application can boot. It is a small diagnostic tool, not a replacement for Maven/Gradle packaging.

## 14. End-to-End Diagnostic Workflow

1. Determine whether the target artifact is an executable Boot JAR or a plain library JAR.
2. Identify the module containing the application class.
3. Verify the class is in the main source set.
4. Verify the method is `public static void main(String[])`.
5. Verify the package and FQCN.
6. If multiple main classes exist, select one entry point for the artifact.
7. Configure `mainClass` in the Spring Boot Maven/Gradle Plugin.
8. Run a clean build using the Wrapper.
9. Confirm the class compiled.
10. Confirm the archive has Boot layout.
11. Read the manifest and verify `Start-Class`.
12. Run `java -jar` on the right file.
13. If the wrong app launches, check classifier, output directory, and stale artifacts.
14. If runtime fails to load a class after the entry point is fixed, check dependencies/modules/classloaders.

### 14.1. Maven Command Sequence

~~~bash
./mvnw -B -ntp clean package
javap -classpath target/classes -public com.example.catalog.CatalogApplication
jar tf target/catalog-app-1.0.0.jar
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
java -jar target/catalog-app-1.0.0.jar
~~~

### 14.2. Gradle Command Sequence

~~~bash
./gradlew --no-daemon clean classes bootJar
javap -classpath build/classes/java/main -public com.example.catalog.CatalogApplication
jar tf build/libs/catalog-app-1.0.0.jar
unzip -p build/libs/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
java -jar build/libs/catalog-app-1.0.0.jar
~~~

On Windows without `unzip` by default, use `jar xf` to extract the manifest and then `Get-Content`. `javap` and `jar` come with the JDK.

## 15. Common Mistakes and How to Fix Them

**1. No `main` method.** Class only has `@SpringBootApplication`. Add `public static void main(String[] args)` and call `SpringApplication.run`.

**2. `main` method is not `public`.** Make it `public` so the Java launcher can call it.

**3. `main` method is not `static`.** Java 17 requires a `static` main.

**4. Wrong return type.** Use `void`, not `int` or another type.

**5. Capitalized method name.** `Main` is not `main`; fix the spelling.

**6. Parameter is not a `String` array.** Use `String[]` or `String...`.

**7. Main class resides in `src/test/java`.** Move it to `src/main/java` if it is the app entry point.

**8. Wrong FQCN configured.** Check the package declaration, class name, and casing.

**9. Class has not compiled.** Run `compile`/`classes` and fix compiler errors before `repackage`/`bootJar`.

**10. Plugin placed in the wrong module.** Apply the Boot plugin to the app; core libraries use a plain JAR.

**11. Maven did not run `repackage`.** Check the starter parent, plugin execution, and `package` lifecycle.

**12. Maven auto-selected an unwanted main class.** Set `mainClass` in `spring-boot-maven-plugin`.

**13. Gradle `bootJar` picked the wrong entry point.** Set `springBoot.mainClass` or `bootJar.mainClass`.

**14. Multiple main classes exist.** Pick an FQCN for the artifact; do not depend on auto-detection order.

**15. Configured main class in `maven-jar-plugin`.** Spring Boot `repackage` manages the manifest. Move the configuration to Spring Boot Maven Plugin.

**16. Put app class in `Main-Class` of Boot manifest.** `Main-Class` must be the Boot Launcher; the app class goes in `Start-Class`.

**17. Stale `Start-Class` after refactoring.** Update `mainClass`, clean, and rebuild.

**18. Built the root aggregator by mistake.** Run from the right module or use `-pl`/`-am` and task paths.

**19. Generated main class missing from source set.** Register the generated source directory and task dependency before compilation.

**20. Wrong generated class name in Kotlin.** Check the `Kt` suffix or `@JvmName` and configure the resulting FQCN.

**21. Running the plain JAR by mistake.** Check `BOOT-INF` and manifest; pick the `repackage`/`bootJar` output.

**22. Stale artifacts left in `target`/`build`.** Run `clean` before inspecting output.

**23. Multiple artifacts with classifiers.** Check output directory, classifier, and task; pick the right file.

**24. Build succeeds, yet `java -jar` reports `no main manifest attribute`.** You might be running a plain JAR or `repackage` did not run. Inspect the archive/manifest.

**25. Main class exists in source, missing from JAR.** Check module, source set, compile output, and archive configuration.

**26. Manifest has the right `Start-Class`, yet `ClassNotFoundException`.** Confirm the class actually exists in `BOOT-INF/classes`, in the right package, and in the right artifact.

**27. `NoClassDefFoundError` after fixing entry point.** This is a dependency/runtime classpath issue. Inspect `BOOT-INF/lib`, dependency scopes, and resolution.

**28. Multiple apps wanting one JAR selected by profile.** An archive's `Start-Class` is fixed. Split artifacts/modules or use one main class that intentionally dispatches by profile/command.

**29. Applying Boot plugin to a library just because it has a demo `main`.** A library does not need an executable archive. Use the Java Library plugin and separate the demo app if needed.

**30. Not inspecting the artifact after building.** Build success does not prove `Start-Class` is right. Read the manifest and run the exact JAR file.

## 16. Pre-Release Checklist for Executable JARs

- [ ] Identified the right application module.
- [ ] Main class resides in the main source set.
- [ ] Class has `public static void main(String[] args)`.
- [ ] Package and FQCN are accurate and case-sensitive.
- [ ] If multiple main classes exist, an explicit entry point is selected.
- [ ] Maven: `spring-boot-maven-plugin` has the right `mainClass`.
- [ ] Gradle: `springBoot.mainClass` or `bootJar.mainClass` is right.
- [ ] Did not misconfigure `maven-jar-plugin` or the `jar` task.
- [ ] Plugin is applied in the app module, not core/root aggregator.
- [ ] Clean build completed.
- [ ] Class appears in `target/classes` or `build/classes/java/main`.
- [ ] Executable archive has Boot layout.
- [ ] Manifest has the Boot Launcher in `Main-Class`.
- [ ] Manifest has the application FQCN in `Start-Class`.
- [ ] Executed `java -jar` on the right artifact.
- [ ] If multi-module, artifact and classpath come from the right module.
- [ ] If Kotlin, used the generated JVM class name.
- [ ] If an executable is not needed, use a plain JAR instead of forcing `repackage`.

## 17. Official References

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Configuring Executable Archive Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Executable JAR Launcher and Manifest: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html
- Oracle Java 17 — JAR File Specification and Main-Class: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Oracle Java 17 — java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 17 — javap tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle 8.5 — Java Plugin and Source Sets: https://docs.gradle.org/8.5/userguide/java_plugin.html

**Conclusion:** When Spring Boot reports no main class found or multiple main classes, verify that the entry point class has the valid Java 17 signature and resides in the main source set. Then configure the **FQCN** directly in the Spring Boot Maven/Gradle Plugin. Inspect the Boot Launcher's **Main-Class**, the application's **Start-Class**, the archive contents, and the `java -jar` result. An executable Boot JAR needs one explicitly chosen entry point; if you have multiple independent applications, release separate artifacts/modules rather than relying on auto-detection.