# Dependency management in Gradle or Maven

A Spring Boot application rarely uses only classes built into Java. To build REST APIs, connect to a database, handle JSON, log events, or write tests, a project needs many libraries. Each library may itself need other libraries. When you add one dependency, you introduce an entire **dependency graph** into your application, not all of whose components are declared directly.

**Dependency management** is the process of declaring, selecting versions for, resolving conflicts among, and controlling the libraries a project needs at compile, runtime, and test phases. **Maven** and **Gradle** are two popular build tools for Java applications. Spring Boot adds **starters** and a managed set of library versions to reduce manual assembly work.

This lesson explains how to declare dependencies, the role of the BOM, how Spring Boot supports both Maven and Gradle, and how to verify which versions are actually used.

## 1. How do dependencies, repositories, plugins, and build tools differ?

| Concept | Role | Example |
| --- | --- | --- |
| Dependency | A library providing APIs or functionality the application needs | `spring-boot-starter-web`, PostgreSQL JDBC driver |
| Repository | Where the build tool finds and downloads artifacts | Maven Central, internal artifact repository |
| Build plugin | Extends the build, run, and packaging process | `spring-boot-maven-plugin`, Gradle plugin `org.springframework.boot` |
| Build tool | Reads the project description, resolves dependencies, and executes build tasks | Maven, Gradle |

Keep this distinction clear: declaring a repository does not add libraries automatically; declaring a Spring Boot plugin does not mean the application already has Spring MVC. A plugin controls **the build process**, whereas a dependency supplies code and resources used by the application or tests.

Maven typically uses `pom.xml`. Gradle typically uses `build.gradle` (Groovy DSL) or `build.gradle.kts` (Kotlin DSL). Both can download artifacts, compute dependency graphs, and compile applications, though they differ in syntax and certain version resolution rules.

## 2. How is a dependency identified?

Artifacts in the Maven ecosystem typically have coordinates:

~~~text
groupId : artifactId : version
~~~

For example:

~~~text
org.springframework.boot : spring-boot-starter-web : 3.3.5
~~~

`groupId` identifies the publishing organization/group, `artifactId` identifies the artifact, and `version` selects a specific release. An artifact may also include a packaging or classifier in special cases, but those three components suffice for an introductory lesson.

Direct declaration in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.3.5</version>
</dependency>
~~~

Equivalent Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
}
~~~

Both examples above **specify the version explicitly**. In Spring Boot projects, we usually manage versions in one shared location so dependencies align consistently. That is why later you will often see declarations without a `version`.

### 2.1. Direct and transitive dependencies

A **direct dependency** is a library the project explicitly declares in its build file. A **transitive dependency** is a library required by another dependency and brought in via metadata.

For instance, the project declares the web starter:

~~~mermaid
flowchart TD
    A["Application"] --> B["spring-boot-starter-web"]
    B --> C["Spring MVC"]
    B --> D["JSON support"]
    B --> E["Embedded servlet container"]
    D --> F["Jackson libraries"]
    E --> G["Tomcat libraries"]
~~~

Exact artifact names and graph edges vary by Boot version; the diagram illustrates the roles of the component groups.

A library can appear via multiple branches:

~~~text
Application
   ├── library-A ───► common-lib:1.0
   └── library-B ───► common-lib:2.0
~~~

In this case, the build tool must select the final version of `common-lib` on the classpath based on conflict resolution rules and active dependency management.

### 2.2. There is more than one kind of classpath

The **classpath** is the set of classes, libraries, and resources visible to a Java task. A project typically has multiple classpaths:

- Classpath for compiling main code.
- Classpath for running the application.
- Classpath for compiling and running tests.
- Dedicated classpaths for annotation processors or build plugins.

For example, JUnit is needed for testing but usually does not need to be packaged into the production runtime. A JDBC driver can be declared runtime-only if source code does not directly reference driver-specific classes.

Distinguishing scopes or configurations helps the project place the right libraries into the right phases.

## 3. What problems do Spring Boot starters and the BOM solve?

Spring Boot provides **starters**: dependencies that group commonly used libraries for a capability, helping you get started faster.

For example:

| Starter | Capability group |
| --- | --- |
| `spring-boot-starter-web` | Web applications based on Spring MVC |
| `spring-boot-starter-validation` | Jakarta Bean Validation |
| `spring-boot-starter-data-jpa` | Spring Data JPA |
| `spring-boot-starter-security` | Spring Security |
| `spring-boot-starter-test` | Common testing tools |
| `spring-boot-starter-actuator` | Endpoints and integrations for application observability |

Starters help answer: **“Which libraries do I need for this capability?”**

Spring Boot also provides a **BOM (Bill of Materials)** with coordinates:

~~~text
org.springframework.boot:spring-boot-dependencies:<boot-version>
~~~

The BOM describes managed versions for many artifacts compatible with a Spring Boot release. It helps answer: **“If I use these libraries, which versions should I use?”**

Illustrative example with Spring Boot `3.3.5`:

~~~text
org.springframework.boot:spring-boot-dependencies:3.3.5
~~~

This version is used consistently across the lesson to illustrate the mechanism, not to recommend it as the latest version for every project. When creating a real project, choose a supported Spring Boot version compatible with your JDK, plugins, and system libraries.

**The BOM does not automatically add all dependencies to the project.** It supplies version management metadata for dependencies that are declared or pulled in transitively according to the build tool's rules.

| Spring Boot starter | Spring Boot BOM |
| --- | --- |
| Usually a dependency you add to the project | Metadata managing versions |
| Pulls in libraries needed for a capability | Does not automatically pull in every managed library |
| Example: `spring-boot-starter-web` | `spring-boot-dependencies` |
| Selects a **feature group** | Coordinates **versions** |

An application can use both a starter to gain web capabilities and the BOM to avoid manually assigning versions to every dependency.

## 4. Maven: managing dependencies with the Spring Boot parent

For a first Spring Boot project, the most common approach is inheriting `spring-boot-starter-parent`.

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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
~~~

This configuration shows:

1. The Spring Boot parent provides corresponding dependency management and many Maven conventions for plugins/builds.
2. `java.version` declares the Java version used by the project according to Boot parent conventions.
3. Neither starter needs an explicit version because both are covered by the parent's management.
4. The test starter belongs to the `test` scope so it is used for testing.
5. `spring-boot-maven-plugin` sits in `build/plugins` because it handles building, running, and packaging.

With an appropriate JDK and Maven, you can run:

~~~bash
mvn test
mvn package
mvn spring-boot:run
~~~

`mvn test` runs lifecycle steps up to the test phase; `mvn package` runs the required phases and produces the artifact; `mvn spring-boot:run` starts the application through the Spring Boot plugin.

The downloaded dependency set can include dozens of artifacts even though `pom.xml` only declares two starters.

### 4.1. How does `dependencies` differ from `dependencyManagement`?

`<dependencies>` declares the libraries **the module actually needs**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

`<dependencyManagement>` declares version management rules and certain dependency metadata. It can be inherited from a parent or declared inside the POM.

Example of how to import a BOM:

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

**Importing a BOM does not automatically create a REST API.** If you have not declared the web starter in `<dependencies>`, importing the BOM alone will not put Spring MVC on the runtime classpath.

### 4.2. When the project already has its own parent

Maven allows only one direct parent. An enterprise may require all projects to inherit an internal POM, making it impossible to simultaneously inherit `spring-boot-starter-parent`.

In that case, projects typically **import the Boot BOM** inside `dependencyManagement` as shown above, then declare the needed dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Importing the BOM does not carry over the starter parent's entire plugin and lifecycle configuration. If you want an executable JAR, you must configure `spring-boot-maven-plugin` appropriately (including its version and the `repackage` goal when needed) or rely on settings supplied by the internal parent.

Example plugin configuration snippet when not using the starter parent:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
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

In addition to this plugin, a project not using the starter parent also needs to ensure Java compiler configuration and related Maven plugin versions are properly managed. The BOM only covers dependency management.

## 5. Maven scopes: when is a dependency used?

Maven provides several scopes with distinct meanings.

| Scope | Common meaning | Example |
| --- | --- | --- |
| `compile` | Default; typically used for compilation and runtime | Spring MVC starter |
| `provided` | Available at compile time, but the deployment environment is expected to supply the dependency | Servlet API in certain WAR models |
| `runtime` | Not needed directly at compile time, but required to run | JDBC driver |
| `test` | Used for compiling and running tests | Spring Boot test starter |
| `system` | Points to a local JAR path; generally should be avoided | Special legacy code |
| `import` | Used inside `dependencyManagement` to import a POM-type BOM | Spring Boot BOM |

PostgreSQL driver example:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

If the Boot BOM manages the corresponding driver version, you can omit the version. However, declaring the driver is **not enough** to connect to the database: the application still needs datasource configuration, a running database, and appropriate data access libraries.

Maven scopes also affect dependency transitivity. You should not put an entire test library onto the compile classpath just to quickly fix a broken import.

## 6. Gradle: dependency management with plugins and BOM

Gradle organizes libraries via **configurations**. With the Java plugin, familiar configurations include `implementation`, `runtimeOnly`, and `testImplementation`.

There are two common ways to use Spring Boot-managed versions:

- Combining the Spring Boot Gradle plugin with the `io.spring.dependency-management` plugin.
- Using a Gradle native BOM via `platform(...)`.

Both approaches have different version resolution semantics. Choose one consistent strategy and inspect resolved dependencies when needed.

### 6.1. Option A: `io.spring.dependency-management`

Example `build.gradle` using Groovy DSL:

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
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In this configuration:

- The `java` plugin creates Java compilation configurations and tasks.
- The `org.springframework.boot` plugin adds tasks such as `bootRun` and `bootJar` in applicable project types.
- The `io.spring.dependency-management` plugin integrates Maven-style dependency management. When combined with the Spring Boot Gradle plugin, it can automatically import the BOM matching the Boot plugin version.
- `repositories` specifies where to download artifacts.
- Dependencies can omit versions because they are managed by the Boot BOM.
- `toolchain` configures Java 21 for relevant build tasks.

**Merely adding the `org.springframework.boot` plugin does not automatically guarantee all versionless dependencies can resolve.** You need the dependency management plugin or a corresponding BOM/constraint mechanism.

Commands when the repository has the Gradle Wrapper:

~~~bash
./gradlew bootRun
./gradlew test
./gradlew bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
.\gradlew.bat test
.\gradlew.bat bootJar
~~~

The wrapper must be present in the project for `./gradlew` or `.\gradlew.bat` to work.

### 6.2. Option B: Native Gradle BOM via `platform(...)`

Gradle supports importing a Maven BOM as **platform constraints**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`platform(...)` introduces the BOM's version constraints into the needed configurations. Declaring it on both `implementation` and `testImplementation` ensures test dependencies also receive managed versions.

Understand one difference: **Gradle native platforms use Gradle's version resolution algorithm**, which is not identical to Maven's `dependencyManagement` or the `io.spring.dependency-management` plugin. If another dependency requests a higher version or tighter constraint, the final result may differ from the BOM suggestion. Use `dependencyInsight` to see why.

Do not use `enforcedPlatform(...)` merely because you want “the BOM to always win.” It imposes stricter constraints and can affect other modules when dependencies are consumed transitively.

### 6.3. Gradle Kotlin DSL

If the project uses `build.gradle.kts`, the syntax is Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))
    testImplementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))

    implementation("org.springframework.boot:spring-boot-starter-web")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Groovy DSL and Kotlin DSL express the same Gradle dependencies and tasks, but use different syntax. Do not copy Groovy syntax like `implementation '...'` directly into a Kotlin DSL file.

## 7. Gradle configurations: which classpath does a dependency belong to?

| Configuration | Role | Example |
| --- | --- | --- |
| `implementation` | Dependencies for application code, typically participating in compile and runtime | Web starter |
| `compileOnly` | Needed when compiling, not automatically placed into runtime | Certain APIs or annotations |
| `runtimeOnly` | Needed at runtime, not required when compiling | JDBC driver in many projects |
| `testImplementation` | Used for compiling and running tests | Test starter |
| `testRuntimeOnly` | Added to test runtime | Certain test engines |
| `annotationProcessor` | Dependencies used for annotation processing during compilation | Configuration processor |

For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

The configuration processor generates metadata to assist tooling when working with Spring Boot configuration; it is not a dependency for handling HTTP requests.

For library projects using the `java-library` plugin, `api` has an additional meaning: dependencies belonging to the library's public API can be exposed to consumers. Standard Spring Boot application projects typically use `implementation`, while public API exposure of library modules should be designed separately.

## 8. How do Maven and Gradle differ?

| Topic | Maven | Gradle |
| --- | --- | --- |
| Build file | `pom.xml` | `build.gradle` or `build.gradle.kts` |
| Dependency declaration | `<dependencies>` and `<dependency>` | `dependencies { ... }` |
| Spring Boot BOM | Parent or `dependencyManagement` BOM import | Dependency Management plugin or `platform(...)` |
| Classpath classification | Scopes `compile`, `runtime`, `test`, etc. | `implementation`, `runtimeOnly`, `testImplementation`, etc. |
| Run Boot app | `mvn spring-boot:run` | `./gradlew bootRun` |
| View dependency graph | `mvn dependency:tree` | `./gradlew dependencies` |
| Investigate version cause | Dependency tree and effective POM | `dependencyInsight` |
| Default version conflict handling | Mediation based on tree distance | Typically selects higher version among resolvable requests, subject to constraints/rules |

You cannot translate each Maven scope directly to a Gradle configuration without considering classpaths. For instance, Gradle's `implementation` both serves the current module's compilation and affects runtime under the Java plugin model; it also hides the dependency from a consumer's compile classpath in library builds. Maven's `compile` scope has different transitivity rules.

## 9. Why do version conflicts occur?

Suppose:

~~~text
Application
    ├── module-A ──► api-lib:1.0
    └── module-B ──► api-lib:2.0
~~~

Some methods may have changed between the two versions. If runtime uses a single version incompatible with one of the modules, an error may surface during startup or when executing a particular code path.

### 9.1. Maven: dependency mediation

Maven typically prefers the dependency closer to the root in the tree (“nearest definition”). If two dependency paths have the same depth, declaration order can influence which version is picked first. Applicable `dependencyManagement` rules can also govern an artifact's version.

Therefore, **you cannot look at a single library POM and conclude which version will run**. You need to inspect the application's dependency tree.

### 9.2. Gradle: version constraints and conflict resolution

Gradle typically picks the highest version among compatible requests, unless constraints, strict versions, forced versions, platforms, or other resolution rules apply. When a native BOM is imported via `platform(...)`, versions from the BOM participate in resolution as constraints.

This explains why the actual version can differ from the BOM's suggestion when another request exists. Do not assume a BOM always “hard-locks” every version in Gradle.

### 9.3. Runtime errors can be dependency-related

Some errors that warrant checking the dependency graph:

~~~text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassNotFoundException: ...
~~~

`NoSuchMethodError` can indicate code called a method missing from the class loaded at runtime. `ClassNotFoundException` can occur because a required dependency is missing from the runtime classpath. `NoClassDefFoundError` can also arise from a class initialization failure, not only a missing JAR.

A specific error should be diagnosed via the stack trace, dependency graph, and actual packaging; not every error is solved by arbitrarily bumping a version.

## 10. Viewing resolved versions with Maven

From the directory containing `pom.xml`:

~~~bash
mvn dependency:tree
~~~

The output shows the dependencies and transitive branches in use. To focus on Jackson:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

To view the POM after applying parent inheritance, properties, and dependency management:

~~~bash
mvn help:effective-pom
~~~

These tools answer different questions:

- **What is declared?** Read `pom.xml`.
- **What version management rules are in effect?** Check the effective POM.
- **What is the final dependency graph?** Check the dependency tree.

If a POM declares a versionless library yet the effective POM has no version management rule for that artifact, Maven can report a missing version error before building.

## 11. Viewing resolved versions with Gradle

With the Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

This command displays the dependency graph for the application's runtime classpath.

To see why a specific version was selected:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

`dependencyInsight` is especially helpful when Gradle picks a version different from what you saw in a dependency declaration. The output helps identify dependency paths, version requests, and relevant resolution rules.

To view test dependencies, select the appropriate test configuration. To view dependencies of the build process or plugins themselves, use appropriate tools and configurations; they are not necessarily on the application's `runtimeClasspath`.

## 12. Adding a new dependency with a verifiable workflow

Suppose you need to validate input data using Bean Validation.

### Step 1: Choose the appropriate dependency

With Spring Boot 3.x, the commonly used starter is:

~~~text
org.springframework.boot:spring-boot-starter-validation
~~~

### Step 2: Declare it in the right place

Maven, if a parent/BOM is already configured:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle, if a BOM is already applied:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

### Step 3: Resolve and compile

Maven:

~~~bash
mvn compile
~~~

Gradle:

~~~bash
./gradlew compileJava
~~~

The build tool downloads dependencies from repositories, computes versions, and sets up the classpath. If an error occurs at this step, inspect coordinates, repositories, or the version management source first.

### Step 4: Use the added capability

Example DTO in Spring Boot 3.x:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(@NotBlank String name) {
}
~~~

In a Spring MVC controller:

~~~java
@PostMapping("/users")
public ResponseEntity<String> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.ok("Created: " + request.name());
}
~~~

The controller snippet above illustrates using `@Valid` and `@RequestBody`; it requires Spring MVC/Jakarta Validation imports and a valid controller setup to compile in a project.

The new dependency makes Bean Validation available, yet the application still has to declare constraints and trigger validation at the right places. **Having a dependency on the classpath does not mean desired behavior happens automatically.**

### Step 5: Verify the result

Once it builds, run tests or send valid and invalid requests. If you need to confirm specific versions, use `dependency:tree` / `dependencyInsight`.

This is a useful working loop: **identify feature → select dependency → declare right scope → resolve → use API → observe behavior**.

## 13. Overriding versions: when and how?

The Spring Boot BOM starts you off with a version set selected for your Boot line. Occasionally you need to upgrade an artifact due to a security fix, bug fix, or new feature requirement.

Before overriding, check:

1. What version is currently resolved?
2. Is the library inside the Boot BOM?
3. Does a newer Boot release address the need via a coordinated version set?
4. Is the new version compatible with Spring Framework and related libraries?
5. Are there tests verifying the affected features?

In Maven, you can declare an explicit version for a dependency outside the BOM:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>some-library</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

These are **illustrative** coordinates. For managed dependencies, a project can use `dependencyManagement` or starter parent override properties in the manner supported by that Boot version.

With Gradle:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.example:some-library:1.4.0'
}
~~~

An explicitly written version still participates in Gradle's resolution algorithm alongside other constraints; inspect `dependencyInsight` before drawing conclusions.

**Do not override versions of multiple related libraries with mismatched numbers without understanding their compatibility relationships.** For example, Jackson modules generally need to stay aligned on the same version line; upgrading Boot or the relevant BOM together is usually easier to control.

## 14. Exclusions: removing pulled-in dependencies

Sometimes a starter brings in a component the project wants to replace with another choice. Build tools allow excluding a transitive dependency at the declaration edge.

Illustrative example of switching Spring Boot's logging starter:

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-log4j2</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
~~~

This is an intentional change for logging requirements, not a mandatory step for every application.

Keep in mind:

- Excluding along one branch does not guarantee removing the artifact from the entire graph if another branch still requires it.
- Removing a dependency can eliminate required classes or services.
- When replacing logging, verify whether other starters bring default logging back in.
- After excluding, inspect the dependency tree and test behavior.

Do not remove a transitive dependency simply because you spot it in the graph without understanding its role.

## 15. Repositories and artifact download failures

Common Gradle repository declaration:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Maven typically includes Maven Central by default and can use `settings.xml` or the POM to declare environment-specific repositories/mirrors.

Common causes when artifact downloads fail:

- Wrong `groupId`, `artifactId`, or version.
- The repository does not host that artifact.
- Network outage, proxy misconfiguration, or DNS/TLS error.
- An internal repository requires authentication.
- The build is running offline without the artifact cached locally.
- Invalid or missing artifact metadata.

If you encounter `401 Unauthorized` or `403 Forbidden` when accessing an internal repository, check credentials configuration and permissions. Never put real secrets in a build file and commit them as a “quick fix” for dependency download failures.

Distinguish **failing to resolve an artifact** from **failing to compile code**. One happens before the dependency is downloaded; the other happens when the compiler checks source code or APIs already placed on the classpath.

## 16. Reproducible builds and version upgrade policies

A maintainable project should be able to rebuild with appropriate dependencies on other machines or in CI.

Habits that improve stability:

- Use explicit Spring Boot and plugin versions.
- Manage dependencies via an appropriate BOM.
- Avoid dynamic versions like `1.+` unless you have governance processes for them.
- Control repositories and artifact sources.
- Upgrade dependencies purposefully, inspect release notes, and run relevant tests.
- Document version change decisions in code reviews when needed.

### 16.1. Gradle dependency locking

Gradle provides **dependency locking** to record resolution results for configurations with locking enabled.

Groovy DSL example:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Then generate/update lock state using appropriate tasks, such as:

~~~bash
./gradlew dependencies --write-locks
~~~

If locking is used, lock files should be tracked alongside source code and updated intentionally when upgrading dependencies. Do not delete a lockfile just to make a version conflict disappear without understanding the root cause.

### 16.2. Maven and version management

Maven uses dependency management, effective POMs, and explicit versions. A basic Maven project does not have a built-in lockfile model directly equivalent to Gradle dependency locking. Organizations can add the Maven Enforcer Plugin, artifact repository mirrors, and upgrade policies to improve reproducibility.

The BOM provides a consistent starting point, yet build reproducibility also depends on plugins, repositories, environment variables, and artifact release workflows.

## 17. What do multi-module projects need to manage?

Suppose a system has the structure:

~~~text
shopping-system/
├── web-api/
├── domain/
└── persistence/
~~~

A sensible relationship could be:

~~~mermaid
flowchart TD
    W["web-api"] --> D["domain"]
    W --> P["persistence"]
    P --> D
    W --> S["Web starter"]
    P --> J["JDBC/JPA libraries"]
~~~

Not every module needs every starter. A pure Java domain module may not need Spring Web or a runtime server. Modules sharing libraries should align on versions, while each module declares only the dependencies it actually uses.

**Maven multi-module** setups often use a parent POM and `dependencyManagement` for shared versions. Each child module declares the dependencies it needs.

**Gradle multi-project** setups can centralize versions via convention plugins, version catalogs, or a shared platform, while each subproject uses appropriate configurations.

The goal is to reduce duplicated version rules and control module boundaries, not to add every library to every module.

### 17.1. Gradle version catalog

A version catalog centralizes aliases and versions, for instance in `gradle/libs.versions.toml`:

~~~toml
[versions]
springBoot = "3.3.5"

[libraries]
spring-web = { module = "org.springframework.boot:spring-boot-starter-web" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
~~~

When the default catalog named `libs` is active, Gradle can reference the dependency via `libs.spring.web`.

However, a version catalog **does not automatically act as a BOM**. For versionless dependency aliases like the example above, the project still needs dependency management or platform constraints in the relevant configurations.

A catalog centralizes naming and project-managed versions; a BOM centralizes compatible versions for a dependency ecosystem; Gradle remains the tool deciding the final resolved graph.

## 18. Common dependency errors and how to narrow them down

### Error A: Maven missing version

The message may contain:

~~~text
'dependencies.dependency.version' for ... is missing
~~~

The project may have declared a versionless dependency without inheriting a parent or importing a BOM that manages that artifact.

**Check:** `pom.xml`, `mvn help:effective-pom`, then verify whether the artifact is covered by the version management source.

### Error B: Gradle cannot resolve a versionless starter

The message may contain:

~~~text
Could not find org.springframework.boot:spring-boot-starter-web:
~~~

One cause is not applying `io.spring.dependency-management` or `platform(...)` to the declared configuration.

**Check:** build script, repositories, BOM, and configurations; do not hastily attach versions to individual starters by guesswork.

### Error C: Build succeeds, runtime reports missing class or method

**Check:** stack trace, runtime classpath, and resolved versions. It may be a version conflict, missing runtime dependency, incorrect exclusion, or unexpected packaging/classloader behavior.

You cannot deduce a single root cause solely from an exception name.

### Error D: Added the driver, yet still cannot connect to the database

The driver provides only one piece of data access. The application may still lack the datasource URL, username, password, a running database, or a data access starter.

**Check:** dependencies, datasource configuration, network, and connection logs in the order of the error.

### Error E: Dependency exists only in tests, yet production runtime needs it

If a dependency is declared `test`/`testImplementation`, it usually is not on the main application's runtime classpath.

**Check:** scope/configuration before searching for bugs in Java source code.

### Error F: A library is requested at multiple versions

**Check:** `dependency:tree` or `dependencyInsight` to locate the conflicting branches. Then evaluate compatibility and decide whether to upgrade Boot, adjust constraints, remove a library, or configure an intentional version.

Avoid removing a transitive dependency before knowing which modules use it.

## 19. Practice: reading and fixing build files

### Exercise 1: Identify roles

Classify the following items:

| Item | Answer |
| --- | --- |
| `spring-boot-starter-web` | Starter dependency |
| `spring-boot-dependencies` | Version management BOM |
| `spring-boot-maven-plugin` | Maven build plugin |
| `mavenCentral()` | Repository configuration in Gradle |
| `spring-boot-starter-test` | Testing dependency |

Explanation: starters are added like libraries, the BOM manages versions, plugins handle builds, and repositories provide artifact downloads.

### Exercise 2: Why does the test starter need the right scope?

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Answer:

1. Does this library serve main sources or test sources?
2. If you remove `<scope>test</scope>`, which classpaths could receive unnecessary libraries?
3. Does the BOM automatically add the test starter if it is not declared?

**Hint:** The test starter serves testing; scope restricts which classpaths receive the library; the BOM does not add dependencies automatically.

### Exercise 3: Spot the Gradle version management error

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Question:** Why might this dependency fail to resolve?

**Hint:** There is no version management source for `implementation`. You can add `implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')` or apply the `io.spring.dependency-management` plugin with appropriate configuration.

### Exercise 4: Choose scope/configuration

A REST API needs:

- Spring MVC to receive HTTP requests and return JSON.
- Spring Data JPA for data access.
- PostgreSQL driver at runtime.
- Libraries for testing controllers.

Common dependencies include:

~~~text
spring-boot-starter-web
spring-boot-starter-data-jpa
org.postgresql:postgresql
spring-boot-starter-test
~~~

Write them in Maven `dependencies` or Gradle `dependencies { ... }` format and indicate the appropriate scope/configuration. Do not forget the version management source (parent/BOM/plugin/platform).

One Gradle Groovy DSL option, assuming the BOM is already applied:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This does not yet create a database or entities. Distinguish **having dependencies** from **the application being configured and running properly**.

### Exercise 5: Find the actual Jackson version

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Record the resolved version. If the artifact is missing, check the configuration or actual dependency set. Explain whether the artifact appears directly or transitively.

### Exercise 6: State the consequences of changing a version

Imagine a teammate changes the version of a JSON library while keeping the Boot BOM unchanged.

Be able to answer:

- Why is the override necessary?
- Which related modules must share the same version?
- Which version does the dependency graph actually select?
- Which tests need to run after the change?
- Would upgrading Boot together as a coordinated release be a better option?

These questions turn dependency changes into evidence-based decisions.

## 20. Key takeaways

**Dependency management is more than build-file syntax.** It involves understanding direct dependencies, transitive dependencies, artifact sources, classpaths, and how a version is chosen when multiple requests exist.

With **Maven**, the easiest Spring Boot starting point is `spring-boot-starter-parent`; when another parent is required, you can import the `spring-boot-dependencies` BOM in `dependencyManagement` and configure the necessary plugins. With **Gradle**, you can use `io.spring.dependency-management` or native `platform(...)`, keeping their version resolution differences in mind.

A reliable approach is: **choose the right starters, declare the right scopes, align BOM and plugins, let the build tool resolve, and inspect the dependency graph whenever changes or conflicts arise**. Once you know where libraries come from and why versions are chosen, you will be in control when building, upgrading, and debugging Spring Boot applications.
