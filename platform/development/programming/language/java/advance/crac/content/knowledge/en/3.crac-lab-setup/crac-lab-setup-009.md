# Declaring `org.crac:crac` in Maven or Gradle

To write Java code using the CRaC API, a project needs to declare the `org.crac:crac` library in its dependency management system. This library provides API types such as `Resource`, `Context`, and `Core`, allowing the application to register callbacks for handling before checkpoint and after restore. How it is declared depends on the build tool the project uses: Maven declares dependencies in `pom.xml`, whereas Gradle declares them in the `dependencies` block of the build file.

The dependency allows the source code to compile and link against the CRaC API. Adding the dependency itself does not turn a regular JDK into a runtime capable of checkpoint/restore. When deploying actual CRaC functionality, the application still needs to run on a JDK or runtime that supports CRaC and an appropriate deployment environment.

## 1. What role does the dependency play?

`org.crac:crac` is a dependency coordinate following Maven conventions consisting of three parts:

| Component | Value | Meaning |
|---|---|---|
| Group ID | `org.crac` | The group publishing the library |
| Artifact ID | `crac` | The artifact name providing the CRaC API |
| Version | Example `1.5.0` | The library version the project wants to use |

When the project declares the dependency, Maven or Gradle searches for the artifact by this coordinate in the configured repositories, downloads the artifact along with any related dependencies if present, and places it on the corresponding classpath.

For example, source code can import the API:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
```

If the dependency is not declared or not placed on the compile classpath, the compiler cannot find the `org.crac` types and reports an error such as `package org.crac does not exist`.

## 2. Declaring in Maven

Maven manages a project's dependencies in the `pom.xml` file. Declare `org.crac:crac` inside the `<dependencies>` element of the module whose source code uses the API.

### 2.1. Direct declaration

Example of the dependency section in `pom.xml`:

```xml
<project>
    <!-- Other project elements are omitted in this example. -->

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>1.5.0</version>
        </dependency>
    </dependencies>
</project>
```

`1.5.0` is an illustrative version for syntax. When applying to a project, choose a version approved by the project and check compatibility with the CRaC JDK/runtime to be used. This example should not be understood as a guarantee that this is always the latest version.

In Maven, the default scope of a dependency is `compile`. If `<scope>` is not specified, the dependency is present on both the compile classpath and the runtime classpath, and is used in the appropriate build phases. This is usually the right choice when the application directly implements classes such as `Resource` and needs those API types at runtime.

### 2.2. Managing the version with a property

To avoid repeating the version number across multiple dependencies or modules, the version can be placed in `<properties>`:

```xml
<project>
    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <crac.version>1.5.0</crac.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>${crac.version}</version>
        </dependency>
    </dependencies>
</project>
```

When an upgrade is needed, you only need to change the `crac.version` value in one place. The `maven.compiler.release` example in the snippet above only illustrates compiler configuration; set the Java level appropriate for the JDK version that the project actually supports.

### 2.3. Multi-module Maven projects

With multi-module Maven, the version can be managed centrally in the `<dependencyManagement>` section of the parent POM:

```xml
<project>
    <properties>
        <crac.version>1.5.0</crac.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.crac</groupId>
                <artifactId>crac</artifactId>
                <version>${crac.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

A module whose source code uses CRaC still must declare the dependency in `<dependencies>` of that module itself:

```xml
<dependencies>
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
    </dependency>
</dependencies>
```

`dependencyManagement` only manages dependency information such as version and default scope; it does not automatically add the dependency to every child module. This separation helps modules use the API explicitly while still standardizing the version across the entire project.

## 3. Declaring in Gradle

Gradle declares libraries in the `dependencies` block. The configuration determines which classpath the dependency appears on and how it is exposed to other modules.

### 3.1. Gradle Groovy DSL

For a `build.gradle` file using Groovy DSL:

```groovy
def cracVersion = '1.5.0'

dependencies {
    implementation "org.crac:crac:${cracVersion}"
}
```

You can use syntax without a variable if the project only declares it in one place:

```groovy
dependencies {
    implementation 'org.crac:crac:1.5.0'
}
```

### 3.2. Gradle Kotlin DSL

For a `build.gradle.kts` file using Kotlin DSL:

```kotlin
val cracVersion = "1.5.0"

dependencies {
    implementation("org.crac:crac:$cracVersion")
}
```

Kotlin DSL uses the `implementation(...)` function call; the dependency coordinate string can interpolate the variable using `$cracVersion`.

### 3.3. Centralizing the version in `gradle.properties`

When multiple modules use the same dependency, the version can be declared in `gradle.properties` at the root project:

```properties
cracVersion=1.5.0
```

In `build.gradle`:

```groovy
def cracVersion = providers.gradleProperty('cracVersion').get()

dependencies {
    implementation "org.crac:crac:${cracVersion}"
}
```

In `build.gradle.kts`:

```kotlin
val cracVersion = providers.gradleProperty("cracVersion").get()

dependencies {
    implementation("org.crac:crac:$cracVersion")
}
```

Both approaches retrieve the same value from `gradle.properties`, helping modules use a consistent version.

### 3.4. Using a Gradle version catalog

For projects using a version catalog, coordinates and versions can be managed in `gradle/libs.versions.toml`:

```toml
[versions]
crac = "1.5.0"

[libraries]
crac-api = { module = "org.crac:crac", version.ref = "crac" }
```

Then reference the alias in `build.gradle.kts`:

```kotlin
dependencies {
    implementation(libs.crac.api)
}
```

With the alias `crac-api`, Gradle generates the accessor `libs.crac.api`. This approach is useful when a project has many modules and wants to centralize the dependency catalog in a single file.

## 4. Choosing the appropriate configuration or scope

When declaring a dependency, it is necessary to choose a configuration appropriate for how the source code uses the API.

| Tool | Common declaration | Meaning |
|---|---|---|
| Maven | No scope declared, defaults to `compile` | Present on compile and runtime classpaths |
| Gradle | `implementation` | Internal dependency of the module, present on the module's compile and runtime classpaths |
| Gradle | `api` | Used when the module is a library and CRaC types appear in the public API that need to be exposed to the consumer's compile classpath |
| Gradle | `testImplementation` | Only serves test source code; insufficient if production code imports the CRaC API |
| Gradle | `compileOnly` | Only present on the compile classpath; only use when the runtime is guaranteed to provide the corresponding API |

For a typical Java application, `implementation` in Gradle or the default `compile` scope in Maven is a straightforward and appropriate choice when the application directly uses the CRaC API.

If the module being built is a library and its public methods, public fields, or generic types expose `org.crac` types to consuming modules, Gradle `api` may be an appropriate choice. If CRaC is only used inside the library's implementation, prefer `implementation` so as not to make the dependency part of the consumer's compile API.

Do not choose `testImplementation` for a dependency that production code needs. Also do not switch to `compileOnly` just to reduce artifact size without determining whether the runtime provides the necessary API classes; missing classes at runtime can lead to class-loading errors such as `NoClassDefFoundError`.

## 5. Using the API after declaring the dependency

After the dependency has been downloaded and placed on the classpath, the source code can implement `Resource` to handle the checkpoint/restore lifecycle.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {

    public CacheResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Put the resource into a safe state before checkpoint.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Recreate or refresh the resource after restore.
    }
}
```

The example focuses on illustrating the API types provided by the dependency. The resource handling part needs to be replaced with logic appropriate for the application, such as stopping running work and closing connections before checkpoint, then reopening connections after restore.

Place the dependency in the module that contains the `CacheResource` class. If the class is in the `infrastructure` module but the dependency is only declared in the `application` module, the `infrastructure` module may fail to compile because its classpath does not automatically receive dependencies declared in another module.

## 6. Verifying that the dependency is resolved

After editing the build file, check that the build tool has found the correct dependency and placed it on the desired classpath.

### 6.1. Maven

Run the following command in the directory containing `pom.xml`:

```bash
mvn dependency:tree -Dincludes=org.crac:crac
```

If the project uses Maven Wrapper, you can replace `mvn` with `./mvnw` on Unix-like environments or `mvnw.cmd` on Windows:

```bash
./mvnw dependency:tree -Dincludes=org.crac:crac
```

The output should show `org.crac:crac` along with the selected version in the dependency graph. If the dependency is not shown, check the module where the command is being run, the declaration location in `pom.xml`, active Maven profiles, and repository configuration.

### 6.2. Gradle

With Gradle, check the dependency in `runtimeClasspath`:

```bash
./gradlew dependencyInsight --dependency crac --configuration runtimeClasspath
```

On Windows, you can run `gradlew.bat` instead of `./gradlew`:

```powershell
.\gradlew.bat dependencyInsight --dependency crac --configuration runtimeClasspath
```

The `dependencyInsight` command shows the selected dependency, the path by which it enters the graph, and the reason Gradle chose that version. If the dependency appears in `compileClasspath` but is missing from `runtimeClasspath`, check whether `compileOnly` or a custom configuration was mistakenly declared.

### 6.3. Verifying compilation

After confirming the dependency graph, run the corresponding compile task:

```bash
# Maven
mvn -q -DskipTests compile

# Gradle
./gradlew compileJava
```

If `org.crac.*` imports are still not recognized, check that the dependency is declared in the right module, whether the build configuration has been re-synced in the IDE, and whether the dependency version was resolved successfully. A successful compile confirms the API is present on the compile classpath; it does not yet prove the current environment can create a checkpoint or restore.

## 7. Distinguishing the API library from a CRaC-enabled JDK

This is an important point when configuring the lab environment:

| Component | Responsibility |
|---|---|
| `org.crac:crac` | Provides Java API types for source code to reference and register resource callbacks |
| CRaC-enabled JDK/runtime | Provides checkpoint/restore execution capability at the runtime level |
| Deployment environment | Provides OS conditions, permissions, and configuration necessary for checkpoint/restore to work |
| Maven or Gradle | Resolves dependencies, builds the classpath, and performs the build |

Therefore, a project can compile successfully after adding `org.crac:crac`, yet still be unable to perform a checkpoint if run on a JDK that does not support CRaC. Conversely, installing a CRaC-enabled JDK does not replace declaring the dependency if the source code needs to import the API and the build does not have it on the classpath.

When choosing a dependency version, check the corresponding release, minimum Java requirement, and guidelines of the CRaC runtime that the project deploys. It is advisable to record the JDK version, library version, and build tool in the environment documentation so the development team can reproduce the same configuration.

## 8. Common configuration errors

### Missing version in Maven

If there is no version in `<dependency>` and no version managed by `<dependencyManagement>`, Maven may report an error about missing version information. Declare the version directly or manage the version in the parent POM.

### Placing the dependency in the wrong module

In a multi-module project, a dependency only takes effect for the module where it is declared according to the corresponding configuration. Add `org.crac:crac` to the module whose source code imports `org.crac.*`; declaring it in another module does not automatically add the dependency to this module's classpath.

### Confusing `dependencyManagement` with `dependencies`

Maven `dependencyManagement` manages versions and metadata but does not add the dependency itself. The module that needs to use the API still must declare the dependency in `<dependencies>`.

### Using the wrong Gradle configuration

If production code imports the API but the dependency is only declared with `testImplementation`, the compile task of the production source set will not have the library. If `compileOnly` is used, the application may compile but lack classes at runtime if the runtime does not provide that API.

### Multiple versions in the dependency graph

Transitive dependencies from other libraries can bring another version of `org.crac:crac` into the graph. Use `mvn dependency:tree` or Gradle `dependencyInsight` to find the source bringing in the dependency and determine the final selected version. Manage versions centrally to avoid modules using inconsistent versions.

### Only adding the dependency and running on any JDK

The dependency provides the API for the build. Checkpoint/restore capability depends on the CRaC JDK/runtime and the deployment environment. Confirm that the running runtime actually supports CRaC before testing checkpoint functionality.

## 9. Recommended configuration workflow

When adding CRaC to a new or existing project, you can follow this order:

1. Identify which module directly uses the `org.crac` API.
2. Identify the target CRaC JDK/runtime and a compatible library version.
3. Declare `org.crac:crac` in `pom.xml`, `build.gradle`, or `build.gradle.kts` of that module.
4. Centralize version management using a Maven property, parent `dependencyManagement`, `gradle.properties`, or a version catalog depending on the project structure.
5. Choose the appropriate scope/configuration; typically use the Maven default compile or Gradle `implementation` for applications.
6. Check the dependency graph and compile task.
7. Run the application on a CRaC-enabled runtime to test checkpoint/restore operations and resource callbacks in the target environment.

Properly declaring `org.crac:crac` helps Maven or Gradle provide the CRaC API to Java source code. Centralized version management, choosing the right scope, and verifying the dependency graph keep the build configuration stable across modules. Finally, the deployment JDK/runtime must be checked separately because the API dependency and checkpoint/restore capability are two different parts of the CRaC environment.
