# Maven Coordinates and the Relationship Between Direct and Transitive Dependencies

## 1. Learning Objectives

In a Spring Boot project, writing what looks like a simple dependency line can pull in dozens of libraries. To build and package correctly, you need to know **which library is being requested**, **which additional dependencies that library brings into the project**, and **what rules determine the final selected version**.

After this lesson, you will be able to:

1. Read Maven coordinates in `groupId:artifactId:version` format, and distinguish module coordinates from `scope`, `type`, `classifier`, and where artifacts are downloaded from.
2. Distinguish a **direct dependency** from a **transitive dependency** from the perspective of the current project.
3. Read a dependency graph that has multiple paths to the same module and explain why a dependency is selected or omitted.
4. Distinguish **dependency declarations** from **version management via BOM** and the **actual resolved result**.
5. Use Maven/Gradle to trace the path that pulls in a library, verify the selected version, and identify compile/runtime/test classpaths.
6. Avoid packaging errors caused by missing dependencies, version conflicts, and using transitive library APIs without declaring them directly.

**Scope:** This is the foundational lesson in the **Dependencies and BOM** section of **Spring Boot Build Tooling Packaging**. The focus is on dependency identity and relationships. Artifact publishing workflows, supply chain security, testing, and framework upgrade strategies are only covered to the extent needed to understand their impact on build/packaging.

## 2. What Are Maven Coordinates?

In the Maven ecosystem, a dependency is usually identified by three key parts:

~~~text
groupId : artifactId : version
~~~

Examples:

~~~text
org.springframework.boot : spring-boot-starter-web : 3.3.5
com.fasterxml.jackson.core : jackson-databind : 2.17.2
org.slf4j : slf4j-api : 2.0.13
~~~

The versions above only illustrate coordinate syntax and are **not instructions to manually pick versions for a Spring Boot application**. In real projects, versions can be centrally managed by a BOM or platform.

| Component | Meaning | Example |
| --- | --- | --- |
| `groupId` | Group/organization publishing the module in the artifact ecosystem | `org.springframework.boot` |
| `artifactId` | Name of the artifact/module within that group | `spring-boot-starter-web` |
| `version` | Requested or finally selected artifact version | `3.3.5` |
| `type` / extension | Artifact type, typically defaulting to `jar` for regular Java dependencies | `jar`, `pom`, sometimes `war` |
| `classifier` | Additional variant, when the published artifact has a classifier | `sources`, `javadoc`, platform-specific classifiers |
| `scope` / configuration | Specifies which phase/classpath the dependency applies to; this is a **usage relationship**, not part of GAV | Maven `test`; Gradle `implementation` |

Important: Maven coordinates are **not** Java package names. A library with `groupId` `org.apache.commons` can easily contain Java packages with different naming conventions; nor should you guess an artifact solely by looking at a class name.

When stored in a Maven repository using the standard layout, coordinate components map to a path roughly like:

~~~text
groupId with dots replaced by / / artifactId / version / artifactId-version.jar
org/springframework/boot/spring-boot-starter-web/3.3.5/spring-boot-starter-web-3.3.5.jar
~~~

This example describes the **repository layout** and does not guarantee every repository, classifier, or artifact type has the exact same path/extension. Maven/Gradle also read **POMs and metadata** to learn about dependencies, scopes, variants, and other rules. A JAR is only the binary artifact; POM/metadata help the build tool understand how the module connects to the rest.

### 2.1. Coordinates in a Maven POM

A Maven XML declaration looks like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
</dependencies>
~~~

Here `groupId`, `artifactId`, and `version` describe the module to use. When `version` is managed by `dependencyManagement` or a BOM, you can **omit the version** on that dependency itself, provided proper version management exists in the effective POM.

### 2.2. The Same Module in Gradle

With Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
}
~~~

The coordinate string `group:name:version` is a shorthand notation. `implementation` is a **declared configuration**, not part of the module's identity.

With Kotlin DSL, the equivalent is:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.3.5")
}
~~~

Gradle also uses Gradle Module Metadata, attributes, and variants to select the right components of a module. Therefore, **having the same GAV does not mean every configuration always resolves the exact same file or dependency set**. For ordinary Java applications, the jar/POM model remains the easiest starting point.

### 2.3. Distinguishing Artifact Dependencies from Plugins

A dependency in `dependencies` is used when compiling/running the program. A **build plugin** adds tasks and logic to the build, such as `org.springframework.boot` in Gradle `plugins` or `spring-boot-maven-plugin` in Maven `build/plugins`. A plugin has its own identity, version, and dependencies, and having a name similar to a runtime library does not automatically put it on the application's classpath.

## 3. Direct and Transitive Dependencies

Suppose project `app` declares library `B`, and `B` declares library `C`:

~~~text
app
 └── B       (direct for app)
      └── C  (transitive for app; direct for B)
~~~

A **direct dependency** is a relationship actively declared by the current project in its build file. A **transitive dependency** is a dependency coming from the metadata of another dependency (potentially across multiple levels). Whether something is called "direct" or "transitive" **depends on your point of view**: `C` is direct for `B` but transitive for `app`.

A model closer to real-world Spring Boot:

~~~text
Application (app)
 └── org.springframework.boot:spring-boot-starter-web
      ├── org.springframework.boot:spring-boot-starter
      ├── org.springframework.boot:spring-boot-starter-json
      │    └── com.fasterxml.jackson.core:jackson-databind
      ├── org.springframework.boot:spring-boot-starter-tomcat
      ├── org.springframework:spring-web
      └── org.springframework:spring-webmvc
~~~

The diagram has **simplified** edges, many sub-libraries, and versions, solely to illustrate the role of a starter. The actual dependency graph may vary by Spring Boot version, excludes, profiles, variants, and build configuration.

If `app` only declares `spring-boot-starter-web`, that is a direct dependency. `jackson-databind` may arrive via `spring-boot-starter-json`, making it a transitive dependency of `app`. If `app`'s own code uses `com.fasterxml.jackson.databind.ObjectMapper`, you are using **an API from a transitive library**. That compilation might succeed today, but the app's dependency contract is not yet explicitly expressed.

### 3.1. Why Do Build Tools Follow Transitive Dependencies Automatically?

The build tool reads the requested module's metadata, continues processing effective dependencies, determines suitable versions, and produces a **resolved dependency graph** for each configuration/classpath. Not every module mentioned in a POM is always placed on every classpath; scope, optional flags, exclusions, platforms, conflict resolution, and variant selection all play a role.

Conceptual workflow:

~~~text
Declaration in app
      |
      v
Locate module by coordinates in repository
      |
      v
Read module POM/metadata and propagatable dependencies
      |
      v
Compute graph + scope/configuration + version constraints/conflicts
      |
      v
Resolved classpath for compile / runtime / test / other tasks
      |
      v
Tasks compile, test, bootJar, image... use the appropriate classpath
~~~

An actual graph often has multiple paths pointing to the same module rather than being a simple tree with no converging branches. A dependency appearing multiple times in the printed graph does not mean its JAR is put on the classpath multiple times.

### 3.2. Should You Directly Declare Every Transitive Dependency?

**You do not need to redeclare every internal library of a starter.** The benefit of a starter is providing a coordinated set of dependencies. However:

- If **app source code directly calls APIs of library X**, you should declare X as a direct dependency, even if X is currently pulled in by a starter. This makes the app's contract explicit and prevents breakage if the starter changes its dependencies.
- If X is only an implementation detail of library Y and the app does not use X's API, typically let Y manage its relationship with X to avoid unnecessary version pinning.
- If X plays a clear runtime role that the app directly needs (such as a JDBC driver), declare X with the appropriate configuration/scope instead of hoping another branch pulls it in.
- If you need to control X's version for compatibility or security vulnerabilities, use a BOM, dependency management, constraints, or an intentional declaration, then verify the **resolved version**. Simply adding an arbitrary declaration does not guarantee every tool will pick the desired version.

## 4. Runnable Example: Java 17, Maven, and Jackson

The example below intentionally uses `spring-boot-starter-web` to demonstrate that a transitive library can be visible to Java sources on the compile classpath. We do not need to run a Spring Boot HTTP server yet. The goal is to inspect the **dependency graph**, then promote the dependency actually used in code to **direct**.

**Prerequisites:** JDK 17+ and Maven with access to a repository containing the dependencies; Spring Boot version `3.3.5` is a released illustrative version, not a recommendation for the latest version. This is a standard Maven project; **executable Spring Boot JAR packaging is not configured**.

Create the structure:

~~~text
demo-dependency/
 ├── pom.xml
 └── src/
      └── main/
           └── java/
                └── demo/
                     └── Main.java
~~~

Complete contents of `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example.learning</groupId>
    <artifactId>demo-dependency</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation: `spring-boot-dependencies` is **imported in `dependencyManagement`**, so it provides managed versions for the starter and related libraries. Importing a BOM **does not automatically add all those libraries** to the project. The entry in `dependencies` is what declares the starter actually needed.

Contents of `src/main/java/demo/Main.java`:

~~~java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class Main {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode json = mapper.readTree("{\"ready\":true}");
        System.out.println(json.path("ready").asBoolean());
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn compile exec:java -Dexec.mainClass=demo.Main
~~~

Output printed by the program itself:

~~~text
true
~~~

Maven may print additional download/plugin logs before or after that line; `true` is the **stdout of `Main.main`**, not the entire Maven log.

Why does it compile even though `pom.xml` has not declared `jackson-databind`? Because `ObjectMapper` is on the compile classpath via a transitive dependency from the starter. Verify:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

The concrete output will include versions, scopes, and other branches; do not assume a complete dependency tree without running the command in a real environment.

**Step to improve the dependency contract:** because `Main.java` **directly imports** Jackson APIs, add **inside** `<dependencies>` of `pom.xml`:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

The Maven BOM still manages the version; there is no need to copy an arbitrary Jackson version. After adding it, Jackson becomes a **direct** dependency of the app. It may still exist through the starter-web -> starter-json path, but the app -> Jackson relationship is now explicit. Run `mvn dependency:tree` again to confirm the actual resolved version.

**Packaging note:** By default, the POM above creates a regular JAR during the `package` lifecycle; it has not added the Spring Boot Maven plugin/repackage or a Spring Boot main class. Therefore, **do not** assume you can run `java -jar target/demo-dependency-1.0.0.jar` to start a server. This example demonstrates dependency paths and compiling/running with the exec plugin, not Boot executable archive packaging.

## 5. Equivalent Example with Gradle (Groovy DSL)

To inspect the same graph with Gradle, you can use the `application` plugin instead of enabling full Spring Boot packaging. Keeping `src/main/java/demo/Main.java` the same as in section 4, create `settings.gradle`:

~~~groovy
rootProject.name = 'demo-dependency'
~~~

And `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

application {
    mainClass = 'demo.Main'
}
~~~

`application` applies the Java plugin and adds tasks to run a Java application. `platform(...)` imports the BOM using Gradle's native support to manage versions, while `implementation '...:spring-boot-starter-web'` is a direct dependency. **The example does not apply the `org.springframework.boot` plugin**, so there is no `bootJar` task.

If the project has a Gradle Wrapper compatible with the JDK/Gradle in use:

~~~bash
./gradlew run
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`. If there is no Wrapper yet, use an installed compatible Gradle version or initialize the Wrapper following project conventions. In an environment where libraries can be downloaded, `demo.Main` will print:

~~~text
true
~~~

The `dependencies` command shows which modules appear in each configuration; `dependencyInsight` helps explain **why** a module was selected and the related paths. Since you use the Jackson API directly in `Main.java`, add to `dependencies`:

~~~groovy
implementation 'com.fasterxml.jackson.core:jackson-databind'
~~~

The imported BOM will supply the appropriate version for modules in its managed list. Not all libraries outside the ecosystem are managed by the BOM; if a coordinate has no version and no matching constraint, resolution may fail.

**Comparing the two examples:** Maven expresses version management via `<dependencyManagement>`; this Gradle setup uses `platform()`. Both still require declaring **actual usage of the starter** before transitive modules are resolved. Seeing a dependency in the graph is not enough to conclude it is direct; you must check the app's root declarations.

## 6. BOMs Manage Versions, Not Automatic Dependency Inclusion

A **BOM (Bill of Materials)** is a POM containing a list of coordinates with managed versions/scopes to keep related libraries compatible. A BOM answers: *"When the project needs module X, which version from the recommended set should be used?"* Actual dependency declarations answer: *"Does the project need module X?"*

### 6.1. Maven: dependencyManagement and dependencies

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

This is the **management block**. It is not equivalent to:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

This is the **usage declaration block**. The starter's version can be omitted because management has been applied. Maven also supports using `spring-boot-starter-parent` as the parent POM; in that case dependency management is inherited from the parent and you do not need to import the BOM using the pattern above. The two approaches differ in overall POM setup, but both serve the same version-management idea.

`dependencyManagement` can also affect the version of **transitive dependencies** when coordinates match. However, dependencies with an explicitly declared `<version>` and POM/BOM merging rules can produce unexpected results. Always inspect the **effective POM** and dependency tree when in doubt.

### 6.2. Gradle: platform and dependency constraints

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

In Gradle, `platform` turns a BOM into version constraints on the effective configurations. A **regular platform** provides recommended versions that can still be pushed to another version by other requirements/constraints in the graph. `enforcedPlatform` enforces versions more strictly and can affect consumers outside the current project when used in a library; only use it when you understand the consequences. Do not assume `platform` is an absolute version lock.

The Spring Boot Gradle plugin can work with `io.spring.dependency-management` to import the BOM matching the Boot plugin version. When choosing **native Gradle BOM** support via `platform`, do not assume applying only the Spring Boot plugin activates the same version management. You should know which mechanism your project uses.

### 6.3. BOM vs. Dependency Locks and Version Catalogs

| Mechanism | Function |
| --- | --- |
| BOM / platform | Provides a set of managed/recommended versions, coordinating related libraries |
| Maven `dependencyManagement` | Manages versions, scopes, and settings applied to effective dependencies; does not add dependencies by itself |
| Gradle `libs.versions.toml` (Version Catalog) | Centralizes **declarations** of aliases, coordinates, and versions; does not enforce dependency resolution across the graph by itself |
| Dependency lockfile | Records resolved selection results to support repeatable builds according to tool policy |
| Resolved dependency graph | The final evidence of versions and dependency paths **for a specific configuration** |

A BOM is usually a sensible starting point for Spring Boot because versions have been coordinated for that framework release. However, a BOM **cannot guarantee** that every library outside its managed set is compatible, and overriding one component can break the tested coordination.

## 7. Dependency Scopes: There Is No Single Classpath

A module may be required for compilation without needing runtime packaging, or vice versa. For every build task, ask **"Which configuration/scope is this dependency in?"** before concluding it will be present in the final artifact.

### 7.1. Maven Scopes (Conceptual Model)

| Scope | Typical Intent | Consequences to Remember |
| --- | --- | --- |
| `compile` (default) | Production source library used at compile and runtime | Typically present on compile/runtime classpaths and can propagate transitively |
| `runtime` | Needed only when running, such as a runtime driver | Not a primary compile dependency for application source code |
| `provided` | Needed at compile/test time, but supplied by the deployment environment | Not on Maven's standard runtime classpath; WAR/Boot packaging has specific rules to verify |
| `test` | Library supporting tests | Not automatically placed on the production classpath |
| `import` | Meaningful only inside `dependencyManagement` when importing a POM/BOM | Not a runtime dependency type |
| `optional` (dependency attribute) | Allows consumers to decide whether to pull in the dependency | Optional dependencies do not automatically propagate to downstream consumers like required dependencies |

Maven also has rarer mechanisms like `system`; using local JAR paths instead of repositories/dependency management is discouraged. Maven transitive scopes are computed by **combining scopes across each edge**, so do not assume every `compile` dependency of a library is placed verbatim onto all application configurations.

### 7.2. Gradle Configurations (Java Plugin Model)

| Declared Configuration | Role |
| --- | --- |
| `implementation` | Dependency used for production code; with the standard Java plugin, contributes to the module's compile/runtime classpaths |
| `api` | Declares public API when using the `java-library` plugin; allows consumers to receive the dependency on their compile classpath per the API contract |
| `compileOnly` | Needed at compile time but not placed on the module's runtime classpath via this configuration |
| `runtimeOnly` | Needed only at runtime, not used to compile the module's sources |
| `testImplementation` | Dependency for compiling/running tests, does not become a production runtime dependency |
| `testRuntimeOnly` | Additional dependency needed only when running tests |
| `annotationProcessor` | Processor for compilation; not an application runtime dependency by default |

The **resolvable configurations** such as `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath` represent the final module set after resolution. Gradle features variant-aware dependency management, so the graph can depend on configurations and attributes. For example, the `java-library` plugin distinguishes `api` from `implementation` so implementation details do not leak onto other projects' compile classpaths.

**Impact on Spring Boot packaging:** tasks like `bootJar` use the appropriate runtime classpath configured by the plugin/build. If you put a required JDBC driver in `compileOnly`, compilation may succeed, but running the executable JAR will fail due to the missing driver. If you put a test library in `implementation` instead of `testImplementation`, you may bloat the runtime artifact unnecessarily. To be sure whether a dependency is packaged, inspect **`runtimeClasspath` and the actual archive contents** rather than just reading declaration lines.

## 8. When Multiple Versions Share Coordinates: Maven vs. Gradle

A dependency graph can form a diamond:

~~~text
app
 ├── B
 │    └── D:1.0
 └── C
      └── D:2.0
~~~

Both `D:1.0` and `D:2.0` are requests for **the same module D**, assuming the same groupId and artifactId. A standard runtime classpath does not arbitrarily pack both versions of the same module "to be safe"; the build tool must apply selection rules, and those rules depend on the build system.

### 8.1. Maven: Nearest Definition

By default, Maven prefers the dependency version defined **closest to the project** in the dependency tree. In the diagram above, both paths to D have the same depth; if B is declared before C in the POM, the usual tie-breaker is **first declaration wins**. When app directly declares `D:3.0`, the app -> D relationship is closer than both transitive paths, directly affecting mediation. `dependencyManagement` can enforce a managed version where applicable; check the effective POM to evaluate accurately.

Do not summarize Maven's rule as "always picks the latest version" or "always picks the higher version number." Both statements can be false.

### 8.2. Gradle: Conflict Resolution by Requests and Constraints

By default, Gradle evaluates all requested versions for the same module in the graph and usually selects the **highest version that satisfies all constraints**. With requests `D:1.0` and `D:2.0` and no special rules, the result is typically `D:2.0`. However, `platform`, `enforcedPlatform`, `strictly`, version ranges, dependency constraints, component metadata, and resolution rules can alter the outcome or cause resolution to fail.

Therefore, **declarations that look identical in Maven and Gradle are not guaranteed to produce the same resolved dependency graph**. Especially when the Spring Boot BOM is present, verify the selected version instead of relying on a rule of thumb.

### 8.3. "Declared Version" Differs from "Used Version"

Suppose Gradle prints an arrow:

~~~text
com.example:lib:1.0 -> 2.0
~~~

Standard reading: something requested `1.0`, but resolution decided to use `2.0` for that module in the printed configuration. To see **why** `2.0` was selected, run `dependencyInsight` and read the selection reason/paths. Do not edit build files by guessing just because you saw an arrow.

A project can also suffer a **classpath conflict** when **two artifacts with different coordinates** contain the same class. Version mediation for **a single module** does not automatically resolve every duplicate-class or binary incompatibility issue between differently named libraries.

## 9. Tools for Investigating Real Dependencies

### 9.1. Maven

Run in the directory containing `pom.xml`:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn help:effective-pom
mvn dependency:analyze
~~~

- `dependency:tree` shows Maven's graph after evaluating metadata, scopes, and version mediation; this is where to start finding **which path pulled an unfamiliar module into the app**.
- `-Dincludes=...` focuses on a specific coordinate; results depend on the plugin and effective graph.
- `help:effective-pom` shows the merged POM after inheritance and management, useful when versions are managed in a parent/BOM.
- `dependency:analyze` can point out used-undeclared or unused-declared dependencies; its output is advisory and may miss usage via reflection, annotation processing, or runtime plugins, so verify using knowledge of the application.

If the project has a Maven Wrapper, replace `mvn` with `./mvnw` on Linux/macOS or `.\mvnw.cmd` in Windows PowerShell. Never assume every project has a Wrapper.

### 9.2. Gradle

For projects with a Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

In Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`. In multi-module projects, specify the project path, e.g., `./gradlew :app:dependencies --configuration runtimeClasspath`.

- `dependencies` prints the graph per configuration, showing selected versions, constraints, and repeated branches.
- `dependencyInsight` shows the **selected module, selection reason, and related dependency paths**. When encountering an unexpected version, this is usually the first tool to read.
- `(*)` in some Gradle reports marks a branch already expanded elsewhere to avoid repetition; it does not mean the dependency was omitted.
- Do not compare `compileClasspath` with `runtimeClasspath` and conclude the build is broken just because the two graphs differ; `runtimeOnly` and `compileOnly` exist precisely to make them differ.

### 9.3. Connecting to the Packaged Artifact

When a real project **already has the Spring Boot Gradle plugin and builds an executable JAR with `bootJar`**, you can inspect the packaged contents with JDK `jar`:

~~~bash
jar tf build/libs/actual-artifact-name.jar
~~~

Change the filename to the **exact file generated on your machine**; do not copy a placeholder name. In a standard executable Spring Boot JAR, runtime libraries appear under `BOOT-INF/lib` and application classes under `BOOT-INF/classes`. For Maven Spring Boot repackage, check the actual file in `target/` after the plugin is configured/run.

Inspecting the archive tells you **which files were actually put into the artifact**, while the graph tells you **why and via which dependency path**. When investigating runtime errors, use both. If deploying via an OCI image or layered packaging, also verify the actual image/layers, because a valid dependency graph alone does not prove the image was delivered successfully.

## 10. Excluding or Changing a Transitive Dependency

A transitive dependency may be outdated, incompatible, redundant, or affected by a vulnerability. How you handle it depends on the root cause; **do not disable all transitivity** just to shrink the graph.

### 10.1. Maven Per-Edge Exclusion

If the app directly depends on `B`, and `B` pulls in unwanted `C`, you can declare:

~~~xml
<dependency>
    <groupId>example.group</groupId>
    <artifactId>library-b</artifactId>
    <version>1.0</version>
    <exclusions>
        <exclusion>
            <groupId>example.group</groupId>
            <artifactId>library-c</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

These are **illustrative** coordinates (not guaranteeing the artifact exists in a repository). An exclusion removes transitive propagation along the **B -> C branch** in the app's graph. If another branch also brings in C, C may remain present. Therefore, re-check the dependency tree rather than treating an exclusion as a "global delete."

### 10.2. Gradle Per-Dependency Exclusion

~~~groovy
dependencies {
    implementation('example.group:library-b:1.0') {
        exclude group: 'example.group', module: 'library-c'
    }
}
~~~

Gradle can still pull C back in via another path. Moreover, removing C can cause `ClassNotFoundException` / `NoClassDefFoundError` if B actually needs C at runtime. Before excluding, verify why C is present, which library uses it, and whether a compatible alternative exists.

### 10.3. When a Version Override Is Necessary

Prefer updating the Spring Boot BOM / starter / library providing the dependency whenever possible. If you must override a module, understand that:

- Maven `dependencyManagement` or a direct declaration with a version can affect the selected version.
- Gradle has `constraints`, `strictly`, `platform`, and resolution rules; a line `implementation 'X:1.2'` does not necessarily "force" that version if the graph has other constraints.
- Using `enforcedPlatform` or global force without understanding the consequences can break binary compatibility for other libraries.
- After any change, inspect the **resolved version**, run necessary tests, and verify the runtime artifact.

## 11. Common Errors and Asking the Right Questions

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Java source can import a library, yet `pom.xml`/`build.gradle` does not declare it | The library is a **transitive dependency** | Read the dependency tree; if the app uses the API directly, declare it directly |
| BOM is imported, yet IDE reports missing classes | BOM only **manages versions**, it does not add libraries | Check whether the dependency is declared in `dependencies` and under the right configuration |
| Maven and Gradle select two different versions | Different mediation/constraint rules, parent/platform, or graph | Compare `dependency:tree`, `effective-pom`, `dependencyInsight` |
| `Could not find ...` / artifact resolution error | Wrong coordinates, version, repository, network, or repository permissions | Check GAV, metadata source, repositories, and the actual download error |
| Compiles cleanly, but runtime throws `NoClassDefFoundError` | Missing runtime dependency, wrong scope, exclusion, or improperly packaged artifact | Check runtime classpath, `BOOT-INF/lib`, runtime environment |
| Runtime throws `NoSuchMethodError` after a dependency change | Possible binary incompatibility between compile-time and runtime versions | Inspect selected version, duplicate classes, libraries pulling old/new versions |
| Runtime has two competing logging libraries | Multiple implementations/capabilities present | Identify the provider to keep, inspect the graph and dependency management, then resolve intentionally |
| Edited version directly, yet graph still uses another version | BOM/constraint/nearest-wins/conflict resolution is taking effect | Verify the resolved version and selection reason, not just the declaration line |
| Used `transitive = false` and many classes went missing | Disabled all child dependencies of a module in Gradle | Only use when providing all replacement dependencies yourself; prefer targeted exclusions |
| Test dependency appears in production package | Wrong scope/configuration declared or custom packaging | Check test vs. runtime classpaths, archive files, and task configuration |
| App runs in IDE, but fails in release build | IDE classpath differs from artifact classpath or runtime environment | Compare `runtimeClasspath`, package contents, JDK, and launch command |

**Note:** `ClassNotFoundException`, `NoClassDefFoundError`, and `NoSuchMethodError` can have other causes; the table above provides a starting direction for dependency investigation rather than concluding a single cause from the exception name alone.

## 12. Quick Reasoning Practice

**Scenario A.** The app only declares `spring-boot-starter-web`, and source code calls `ObjectMapper`. Currently compilation succeeds. What might happen if the starter stops bringing Jackson along the same branch?

**Answer:** Compilation of the app can fail because it relied on a transitive API. If the app directly uses Jackson, declare `jackson-databind` directly and let the appropriate BOM manage its version; then inspect the graph.

**Scenario B.** The app imports the Spring Boot BOM and declares no starters. Will `spring-webmvc` and Tomcat automatically appear on the runtime classpath?

**Answer:** No, importing a BOM alone does not pull in all managed libraries. You must declare the dependencies actually needed (for example, the web starter), after which effective transitive edges are resolved.

**Scenario C.** Two branches request the same module at `1.0` and `2.0`. Can you immediately conclude `2.0` will always be packaged?

**Answer:** No. Maven uses nearest-wins; Gradle defaults to the highest version, which can be altered by constraints/strict versions/platforms. You must verify actual resolution and the packaging classpath/task.

**Scenario D.** The app places the JDBC driver in `compileOnly` in Gradle, and when running the packaged artifact it cannot connect to the DB. What could be the reason?

**Answer:** The driver does not appear on the runtime classpath just because it is declared in `compileOnly`. If the application is responsible for providing the driver at runtime, use the appropriate runtime configuration—usually `runtimeOnly`—and verify the dependency graph and actual artifact.

**Scenario E.** The app excludes C from B, yet `dependencyInsight` still shows C. Is the exclusion "broken"?

**Answer:** Not necessarily. Another branch may still request C; excluding on edge B does not globally delete the module. Read all paths bringing C into the graph.

## 13. Checklist When Adding a Library to Spring Boot

1. Identify the exact `groupId` + `artifactId` from official release documentation; do not guess from package/import names.
2. Determine whether the app **directly uses that API** or only uses another library that depends on it internally.
3. Choose the Maven scope / Gradle configuration that accurately reflects compile, runtime, test, or annotation processing usage.
4. Check whether a Spring Boot BOM/parent/platform already manages the version; avoid overriding versions without reason.
5. Resolve the graph for the **relevant configuration**, inspecting paths to the dependency and the final version.
6. When conflicts occur, compare Maven/Gradle rules and choose a reasoned management approach; do not exclude blindly in bulk.
7. Run required compilation/tests, and verify the runtime classpath and actual artifact when packaging/releasing.
8. Document key direct dependencies so future upgrades, license checks, and vulnerability remediation have a clear basis.

### Core Takeaway

**Coordinates** state "which module this is"; **dependency declarations** state "which modules the project needs and where"; **transitivity** explains "which modules come from other modules"; **BOM/constraints** coordinate "which version should be chosen"; **resolved graphs** show "what the build tool actually selected"; and **packaging** decides which files go into the release artifact. Separating these layers helps you read errors accurately and avoid editing the wrong part.

## 14. Official Documentation

- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies.html
- Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle — Dependency Constraints and Conflict Resolution: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
- Gradle — Platforms and Importing Maven BOMs: https://docs.gradle.org/current/userguide/platforms.html
- Spring Boot Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Spring Boot Maven Plugin — Using Spring Boot Dependency Management: https://docs.spring.io/spring-boot/maven-plugin/using.html

Versions listed in examples are illustrative. For real projects, always check the exact **Spring Boot, Gradle/Maven, JDK, and BOM versions in use** before pinning or overriding dependencies.