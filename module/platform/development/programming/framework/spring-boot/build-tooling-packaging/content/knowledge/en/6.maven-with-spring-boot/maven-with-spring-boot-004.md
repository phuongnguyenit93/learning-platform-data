# Declaring and Managing the Version of `spring-boot-maven-plugin`

When developing a Spring Boot application with Maven, simply declaring the `spring-boot-starter-web` or `spring-boot-starter` dependency is not enough to build a proper Spring Boot **executable JAR**. Maven needs a **build plugin** responsible for running the application during development, repackaging JARs/WARs, and handling other build tasks: **`org.springframework.boot:spring-boot-maven-plugin`**.

This lesson focuses on two technical decisions: **where to declare the plugin** and **how the plugin version is selected**. You will practice both common configurations — with and without `spring-boot-starter-parent` — and learn how to inspect the actual version Maven uses and avoid mistakes during upgrades, packaging, or multi-module setups.

The examples use **Spring Boot 3.3.13, Maven 3.9+, and Java 17** for consistency in a reproducible guide. `3.3.13` is an **illustrative version from the 3.3 line**, not necessarily the latest Spring Boot release or the default choice for a new project. In real projects, choose a maintained version suitable for your project's platform and update all version references **consistently**.

## 1. Distinguishing Maven Plugin, Starter, and BOM

Three concepts that are easily confused yet serve different roles:

| Component | Example Artifact | Role | Where in the POM? |
| --- | --- | --- | --- |
| **Maven plugin** | `spring-boot-maven-plugin` | Executes goals **during the build**, such as `run`, `repackage`, `build-image` | `<build><plugins>` or the `<pluginManagement>` section |
| **Spring Boot starter** | `spring-boot-starter-web` | Bundles **application dependencies** such as Spring MVC, JSON, and an embedded web server | `<dependencies>` |
| **BOM** (Bill of Materials) | `spring-boot-dependencies` | Manages **dependency versions** as a compatible set | `<dependencyManagement>` (imported with `type=pom`, `scope=import`) |
| **Starter parent** | `spring-boot-starter-parent` | Inherits the BOM, configures build defaults, and manages Maven plugins | `<parent>` |

Key takeaway: **a Maven plugin is not a runtime dependency of the application.** Declaring `spring-boot-maven-plugin` under `<build>` lets Maven run the plugin's goals; it **does not** turn plugin classes into libraries for controllers/services and does not embed the plugin JAR into `BOOT-INF/lib`.

Similarly, importing the `spring-boot-dependencies` BOM **does not automatically manage the version** of `spring-boot-maven-plugin`. The BOM is imported into **dependency management**, whereas Maven plugin versions belong to **plugin management**.

## 2. Goal, Phase, and Execution: When Does the Plugin Actually Run?

Maven uses **lifecycle phases**, such as `compile`, `test`, `package`, `verify`, `install`. A **plugin goal** is a specific task that can be bound to a phase or invoked directly.

`spring-boot-maven-plugin` provides several common goals:

- `spring-boot:run` — runs the application from the project, convenient for development.
- `spring-boot:repackage` — takes an already-built JAR/WAR and **repackages** it into a Spring Boot archive runnable via `java -jar` when configuration supports it.
- `spring-boot:build-image` — creates an OCI image using plugin-supported tooling; requires a suitable container builder environment.
- `spring-boot:start` and `spring-boot:stop` — support integration/testing workflows.

A typical build flow:

```text
pom.xml
  |
  v
Maven reads parent, dependencyManagement, pluginManagement
  |
  v
compile -> test -> package
                    |
                    +--> maven-jar-plugin builds the initial JAR
                    |
                    +--> spring-boot-maven-plugin:repackage
                         repackages the JAR for java -jar
```

When adding a plugin to `<build><plugins>`, **not every goal runs automatically**. Maven only runs goals invoked directly or bound to the lifecycle via an **execution**. With `spring-boot-starter-parent`, an execution with id `repackage` is already pre-configured; you just declare the plugin in the application's plugin list. Without this parent, you must configure the execution yourself if you want `mvn package` to run `repackage` automatically.

`mvn package` must successfully build the initial JAR before `repackage` processes it. Therefore, running `mvn spring-boot:repackage` alone on a project without an artifact to repackage can fail; use an execution bound to `package` or build with `mvn package` first.

## 3. Approach 1 — Using `spring-boot-starter-parent` (Common Path)

This is the simplest choice when the project **does not need to inherit another parent POM**. The Spring Boot parent already manages versions for many Maven plugins, supplies Java/compiler defaults, and configures the `repackage` execution.

### 3.1. Complete POM

Create `pom.xml` at the project root:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>boot-plugin-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Four points to notice:

1. `<parent>` pins version **3.3.13** of the Spring Boot configuration ecosystem.
2. Starter dependencies **do not need `<version>`** because of inherited dependency management.
3. `spring-boot-maven-plugin` also **does not need `<version>`**, this time because the parent manages the **plugin version** via `<pluginManagement>`.
4. Declaring the plugin in `<build><plugins>` **activates the `repackage` execution configuration prepared by the parent**. No second execution needs to be written.

**Distinguishing the two meanings of "no version needed":** for starters, the version comes from **dependency** management; for Maven plugins, the version comes from **plugin** management. They are two separate sections of the effective POM.

### 3.2. Why Not Rewrite `<executions>`?

When using the parent, the existing configuration is logically equivalent to an execution with id `repackage` calling the `repackage` goal during packaging. Adding another execution with a different id can cause the goal to run **twice**, leading to errors or unexpected artifacts.

If you only want to **customize the existing execution**, use the exact id `repackage`; Section 7 shows how to configure a classifier.

### 3.3. Does the Parent Enable the Plugin Even If the POM Does Not Declare It?

Do not equate **`<pluginManagement>`** with **`<plugins>`**. Plugin management primarily supplies default versions, configuration, and executions **when the plugin is declared or otherwise used**. The explicit, reliable configuration for a runnable application is still declaring `spring-boot-maven-plugin` under `<build><plugins>` as shown. Having only the parent or only a starter dependency does not guarantee an executable archive will be built across all project layouts.

## 4. Approach 2 — Without the Spring Boot Parent, Importing Only the BOM

Many enterprises require a corporate parent, or a multi-module Maven project has its own build parent. Maven allows **only one direct parent**; you can **import the BOM** to manage Spring Boot dependencies, but **you must manage plugin versions and executions yourself**.

### 4.1. Complete POM Without Inheriting Starter Parent

The following standalone `pom.xml` does not declare a Spring Boot parent. It can be adapted to place a corporate parent in `<parent>` if internal standards require one.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>boot-plugin-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Explanation of each part:**

- `<spring-boot.version>3.3.13</spring-boot.version>` is a **project-defined property** so both the BOM and the plugin use the same version.
- `<dependencyManagement>` imports `spring-boot-dependencies`, allowing `spring-boot-starter-web` to omit its version.
- `<version>${spring-boot.version}</version>` on the **plugin** is required here because there is no Boot parent managing plugin versions.
- `<execution><goal>repackage</goal></execution>` binds the goal to the lifecycle (this goal has a suitable default phase) so `mvn package` creates an executable JAR.
- `maven-compiler-plugin` and Java release are declared explicitly so the example is self-contained and avoids relying on compiler defaults from another parent.

When integrating with a corporate parent, inspect `effective-pom` to see which compiler, plugin, execution, and encoding settings the parent already manages; keep only genuinely needed additions. **Importing the BOM does not replace all build configuration from `spring-boot-starter-parent`.**

### 4.2. What If You Import Only the BOM and Forget the Plugin Version?

Maven may attempt to resolve the plugin version elsewhere or emit a warning about a missing version; results can vary by repository and Maven version. This is an **unreliably reproducible** build configuration, even when the application dependency graph is controlled by the BOM.

Pattern to avoid when no matching plugin management exists:

```xml
<!-- Not safe when the project has no Boot parent/pluginManagement -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
```

Fix this by setting `<version>${spring-boot.version}</version>` or managing the version centrally under `<pluginManagement>` and declaring the plugin in modules that need it.

## 5. Where Does Maven Select the Plugin Version From?

When Maven processes a plugin during a build, distinguish among:

1. **Version declared directly** at `<build><plugins><plugin><version>...`: explicitly specifies the version for that plugin.
2. **`<build><pluginManagement>` in the current POM or a valid parent**: supplies version/configuration when the plugin is used without an explicit version.
3. **Maven auto-resolving a version without an explicit source**: can depend on repository metadata and hurt reproducibility. Avoid letting builds reach this fallback.

`spring-boot-starter-parent` falls under case (2). Importing the `spring-boot-dependencies` BOM **does not create a plugin version source in (2)**. `<dependencyManagement>` is also not the place for `spring-boot-maven-plugin`.

To verify which version Maven actually uses, generate the **effective POM** after Maven resolves parents, profiles, properties, and inheritance:

```bash
# Run from the directory containing pom.xml
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

On Windows PowerShell:

```powershell
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
```

Open `target/effective-pom.xml` and search for **`spring-boot-maven-plugin`** inside `<build>`, inspecting `<version>`, `<executions>`, `<id>repackage</id>`, and `<configuration>`. In a project with a parent, the effective POM usually shows both `<pluginManagement>` and active `<plugins>` — distinguish **managed** metadata from executions **actually active**.

Additionally:
- `./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Ddetail` explores goals and parameters (requires resolving the relevant Maven plugins).
- `./mvnw -X package` prints detailed debug logs about plugins/goals executed; enable only when diagnosing issues.
- `./mvnw dependency:tree` inspects **application dependencies**; it is not enough to determine which build plugin version is active.

If the project has no Maven Wrapper, you can use `mvn` instead of `./mvnw` with an installed Maven. Always check `./mvnw -version` or `mvn -version` to confirm which JDK Maven is running on.

## 6. Multi-Module Maven Example: Centralized Management, Selective Activation

An internal parent can manage plugin versions for child modules. Example snippet in a `<packaging>pom</packaging>` parent:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

This is a **configuration snippet to merge into a parent POM**, not a standalone `pom.xml`. In a **runnable application module**, opt in with:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

A **plain library module** omits this plugin declaration and builds a standard library JAR. If you put the plugin with its execution directly into `<build><plugins>` of the parent so every child inherits it, a library module with no main class may unintentionally run `repackage` and fail. **`pluginManagement` fits when you want centralized management while letting each module decide whether to activate the plugin.**

An internal parent must manage **dependency versions and plugin versions as two separate sections**, even if both reference `spring-boot.version`. If a child module declares a different explicit `<plugin>` version, treat that as an intentional override and verify compatibility.

## 7. Customizing `repackage` Properly

### 7.1. Creating an Executable JAR While Keeping the Original JAR

With `spring-boot-starter-parent`, configure **the exact execution id `repackage`** so no second execution is added:

```xml
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
```

This keeps the original JAR artifact and attaches the repackaged artifact with classifier `exec`, typically producing `boot-plugin-demo-0.0.1-SNAPSHOT-exec.jar` alongside the original JAR. When running it, select **the JAR with the classifier**:

```bash
java -jar target/boot-plugin-demo-0.0.1-SNAPSHOT-exec.jar
```

This is a **replacement for the plugin declaration in Section 3.1**, not a second plugin entry inside the same `<plugins>`. When using a corporate parent, check the actual execution id before customizing; do not assume a corporate parent created an execution with id `repackage`.

### 7.2. Specifying the Main Class When Maven Cannot Determine It Unambiguously

If there are multiple `main` classes or you want to specify a particular entry point:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.plugindemo.PluginDemoApplication</mainClass>
    </configuration>
</plugin>
```

Add this inside `<build><plugins>` in a project that **already has an appropriate version/execution** (via parent or explicit management). `mainClass` must be the fully qualified name of the actual main class. Declare it only when genuinely needed: the plugin automatically discovers the main class in many simple projects.

### 7.3. Intentionally Disabling `repackage`

For a module that is **not deployed standalone**, the cleanest approach is usually **not declaring the plugin** in that module. If inheritance or a special workflow still brings in the execution, you can configure `<skip>true</skip>` on the corresponding execution. Do not disable `repackage` on a module that needs `java -jar` without changing its packaging strategy, because `package` output may end up as just a plain JAR.

### 7.4. `repackage` Does Not Replace Other Packaging Tasks

`spring-boot:repackage` **processes an already-built JAR/WAR**; it does not compile Java in place of `maven-compiler-plugin`, does not run tests in place of `maven-surefire-plugin`, and does not turn a `pom` module into an application. Choose `jar` or `war` appropriately and understand plugin/phase ordering when customizing the default lifecycle. For custom packaging setups, verify that the plugin producing the source JAR runs before the Boot plugin repackages it.

## 8. Runnable Hands-On Exercise: Verifying Plugin Version and Executable JAR

You can use **either of the two complete POMs** from Section 3.1 or 4.1. Create the files:

```text
boot-plugin-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── plugindemo/
                        └── PluginDemoApplication.java
```

Contents of `src/main/java/com/example/plugindemo/PluginDemoApplication.java`:

```java
package com.example.plugindemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PluginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PluginDemoApplication.class, args);
    }
}

@RestController
class HealthProbeController {

    @GetMapping("/ping")
    public String ping() {
        return "plugin-ok";
    }
}
```

This is valid Java 17 code. The file has one `public` class matching the filename; the controller is in the same package and does not need to be `public`. `@SpringBootApplication` scans from `com.example.plugindemo` and finds the controller. `spring-boot-starter-web` provides Spring MVC and the default embedded Servlet web server.

**Step 1 — Check Java and Maven:**

```bash
java -version
./mvnw -version
```

If no Maven Wrapper was created, use `mvn -version` and the corresponding `mvn` commands. The JDK running Maven must match the chosen Spring Boot and compiler release.

**Step 2 — Build (and run tests if the project has tests):**

```bash
./mvnw clean package
```

This command resolves plugins and dependencies, compiles Java, and runs `repackage` when properly configured. With either base POM without a classifier, the expected JAR name is:

```text
target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

**Step 3 — Verify the JAR contains the Spring Boot launcher:**

```bash
jar tf target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

For a typical **Spring Boot 3.3.x executable JAR**, you will see paths under `BOOT-INF/classes/`, `BOOT-INF/lib/`, and the loader under `org/springframework/boot/loader/`. For example:

```text
BOOT-INF/classes/com/example/plugindemo/PluginDemoApplication.class
BOOT-INF/classes/com/example/plugindemo/HealthProbeController.class
BOOT-INF/lib/...
```

These lines are **sample paths to look for**, not the entire `jar tf` output. If only compiled classes appear without the Boot loader/`BOOT-INF/lib` structure, `repackage` may not have run or you opened a plain JAR by mistake. A different layout appears if you intentionally configured WAR or another layout.

**Step 4 — Run the packaged artifact:**

```bash
java -jar target/boot-plugin-demo-0.0.1-SNAPSHOT.jar
```

Keeping the process running, open a second terminal:

```bash
curl -s http://localhost:8080/ping
```

The expected HTTP response body is exact:

```text
plugin-ok
```

`curl -s` typically prints the string without a trailing newline, so the terminal prompt may follow immediately on the same line. If `server.port` is not 8080 or the port is busy, use the actual port. Spring Boot startup logs depend on the environment and have no fixed stdout to compare verbatim.

**Step 5 — Prove which plugin version is active:**

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

In the generated file, look for `spring-boot-maven-plugin`, version `3.3.13`, and the applied `repackage` execution. With the parent, version/execution come from inheritance; with BOM import, they come from the explicit plugin declaration in Section 4.1.

On Windows PowerShell, replace `./mvnw` with `.\mvnw.cmd` when using a Wrapper; `java -jar`, `jar tf`, and `curl` run analogously with installed tools.

## 9. Managing Versions When Upgrading Spring Boot

In a project using the Maven plugin to package Spring Boot, **coordinate the plugin version with the Spring Boot dependency/BOM version**. This reduces the risk of mismatches between the loader/build format and the runtime or configuration.

### 9.1. Projects Using the Parent

The primary control point in Section 3.1 is:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>
```

When moving to a suitable newer Spring Boot release, update the **parent version**, review release notes/migration guides, and build/test. In standard setups, both the plugin version and starter dependency management follow the parent. **Do not pin `spring-boot-maven-plugin` to a different version independently without strong justification and testing.**

Note: Maven resolves `<parent><version>` early; do not assume a property declared inside the child POM itself can safely substitute the parent version. Use an explicit version in `<parent>` or a proven organizational parent management strategy.

### 9.2. Projects Not Using the Parent

Update the shared property:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>
```

Both the BOM and the Maven plugin must reference `${spring-boot.version}` as in Section 4.1. This reduces the risk of **upgrading one side while forgetting the other**. Also inspect any corporate parent, other plugin management, other BOMs, and overridden dependency versions to verify the final versions.

### 9.3. Safe Upgrade Procedure

1. Choose a Spring Boot release compatible with your project's JDK, Spring Framework, plugins, and integrations.
2. Update the parent **or** the shared BOM + plugin property together.
3. Run `mvn -version` to verify which JDK Maven uses, especially in CI.
4. Generate `help:effective-pom` to confirm the plugin version and `repackage` execution.
5. Inspect `dependency:tree` to catch incompatible dependency overrides.
6. Run `clean verify`, or at minimum `clean package` and project tests.
7. Inspect the actual JAR/WAR, run the artifact, and verify startup and endpoints.
8. Across major Spring Boot upgrades, read migration guides and check for changed plugin goals/parameters.

**A "newer" Maven plugin version is not automatically "better" if runtime Spring Boot dependencies remain on an older line.** Compatibility of mixed version combinations must be verified against release notes and build/test results.

## 10. Common Errors and Verification Methods

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `mvn package` builds a JAR but `java -jar` does not boot as a Boot executable | Plugin not declared or `repackage` not bound to lifecycle | Check `<build><plugins>`, effective POM, `spring-boot:repackage` goal log, and JAR contents |
| Imported BOM, then Maven warns plugin version is missing | BOM manages dependencies only, not plugins | Set plugin version or inherit proper `<pluginManagement>` |
| Plugin version differs unexpectedly from Spring Boot runtime | Version overridden on plugin, parent, or corporate POM | Check effective POM and dependency tree; align on a tested version set |
| `spring-boot:repackage` reports no source artifact | Goal ran before `package` or wrong plugin execution/packaging | Run `package` with proper execution; verify JAR/WAR was created first |
| `repackage` runs twice | With Boot parent, added a new execution instead of customizing id `repackage` | Keep exact id `repackage` when customizing inherited execution |
| Library module fails complaining no main class found | Plugin/`repackage` applied to every module from parent | Put defaults in `pluginManagement` and activate only in runnable apps |
| Maven cannot find goal `spring-boot:run` or invokes wrong version | Plugin not declared/resolved, missing plugin group/version, or repo issue | Check POM, network/repositories, use explicit plugin coordinates and version |
| `ClassNotFoundException` when running JAR | Runtime dependency excluded, wrong scope, or wrong packaging | Inspect dependency tree/runtime artifact and `BOOT-INF/lib` |
| Changing plugin version works locally but differs in CI | Different Maven/JDK/profiles/settings/repositories, plugin version not pinned | Check Wrapper, `mvn -version`, profiles, effective POM, and repository settings |
| Picked wrong `target/*-exec.jar` or plain JAR | `classifier` produces multiple artifacts | Check filenames and contents with `jar tf`, run the repackaged artifact |
| Invalid `<mainClass>` override | Wrong package/class name or class lacks a suitable `main` | Use the exact fully qualified class name and recompile |
| `spring-boot-starter-web` has managed version but plugin does not | Confused dependency management with plugin management | Check both separate POM sections and declare plugin version when not using parent |

## 11. Checklist When Writing or Reviewing `pom.xml`

- [ ] Determined whether the application **inherits `spring-boot-starter-parent`**.
- [ ] If **using the parent**, declared `spring-boot-maven-plugin` in `<build><plugins>` and relied on parent-managed version/execution unless customization is needed.
- [ ] If **not using the parent**, explicitly managed the **plugin version** and configured `repackage` for apps needing an executable JAR.
- [ ] Did not confuse `<dependencyManagement>` with `<pluginManagement>`.
- [ ] BOM, Spring Boot runtime, plugin, and Java toolchain use intentionally aligned versions.
- [ ] Library modules are not mistakenly repackaged; runnable app modules have a valid main class.
- [ ] Customizing the inherited execution uses the exact id `repackage` to avoid duplicate runs.
- [ ] `help:effective-pom` confirms final versions and executions match intent.
- [ ] `clean package` / `clean verify` passes; `jar tf` confirms archive structure; `java -jar` boots if deployable.

**Memory aid:** `spring-boot-starter-parent` gives you **plugin management and a pre-configured `repackage` execution**; the `spring-boot-dependencies` BOM provides only **dependency management**. When not inheriting the parent, you must explicitly define **version + execution** for `spring-boot-maven-plugin`. The final source of truth is the **effective POM, Maven log, and actual packaged artifact**.

## References

- [Spring Boot Maven Plugin — Using the Plugin (3.3)](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives (3.3)](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)