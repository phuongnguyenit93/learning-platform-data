# BOM and Managing Library Versions Across Compatible Spring Boot Lines

## 1. The Problem: A Starter Must Be Compatible With the Entire Dependency Ecosystem

A custom starter typically connects several components: Spring Boot auto-configuration, Spring Framework, the provider's core library, and several third-party dependencies. If each module picks versions independently, consuming applications may encounter:

- Two Spring Boot modules at different versions.
- Spring Framework modules not belonging to the release line Spring Boot was tested against.
- A runtime library upgraded to a version incompatible with APIs called by auto-configuration.
- Multiple versions of the same library in the dependency graph.
- Applications upgrading Spring Boot while the starter still pulls an outdated dependency set.

**Bill of Materials (BOM)** helps manage a related set of versions as a coordinated unit. Spring Boot publishes the `spring-boot-dependencies` BOM, containing a curated and tested list of dependencies for each release. When an application upgrades Spring Boot and uses that release's BOM, managed dependencies shift to the matching version set.

This lesson uses **Spring Boot 3.3.13 and Java 17** as an illustrative baseline so Maven/Gradle snippets have concrete, reproducible versions. This is an example of how to align release lines, not a statement that every new project today should pick 3.3.13. In real deployments, choose a release line still supported by your organization and read the system requirements and compatibility matrix of the libraries in use.

## 2. What Is a BOM and What Does It Solve?

A BOM is a POM with:

~~~xml
<packaging>pom</packaging>
~~~

and typically contains a block:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Dependencies and versions are managed here -->
    </dependencies>
</dependencyManagement>
~~~

A BOM describes **the versions to use for a group of artifacts**. For example, the Spring Boot BOM manages versions of Spring modules, logging, JSON, database drivers, and many third-party libraries.

When a dependency is listed in the BOM, a project can declare coordinates without repeating versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

If dependency management manages this artifact, Maven resolves the managed version.

### 2.1. A BOM Manages Versions, It Does Not Add Dependencies Automatically

Keep this in mind:

- `dependencyManagement` states that **if the project declares this dependency**, what the default/managed version is.
- `dependencies` is what actually **adds dependencies** to the project.
- Importing a BOM does not automatically place every library in the BOM onto the classpath.
- A BOM also does not create beans, configure auto-configuration, or replace runtime testing.

Example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This snippet only imports the version table. To use MVC, the application still must declare:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

### 2.2. A BOM Is Not a Lockfile

A BOM is a managed/recommended set of versions. The final dependency graph can still be affected by:

- Versions declared directly on dependencies.
- Dependency management from the project/parent or another BOM.
- Dependency mediation and constraints from the build tool.
- Gradle resolution strategies.
- Organization-wide rules/platforms.

Therefore, importing a BOM alone does not prove the runtime classpath is uniform. After configuring it, inspect the dependency tree or dependency insight.

## 3. Choosing the Right Compatible Spring Boot Line

A Spring Boot release ships with a coordinated set of dependencies, including the underlying Spring Framework version. Therefore, do not manually pick separate versions for `spring-core`, `spring-context`, `spring-web`, or `spring-boot-autoconfigure` simply because a newer version exists.

### 3.1. Choose a Release Line Before Choosing Dependencies

When developing a custom starter, determine:

1. Which Spring Boot major/minor line does the library support?
2. What is the minimum Java baseline?
3. Which Spring Framework generation is supported?
4. Which API namespace does the starter use, e.g., `javax.*` or `jakarta.*`?
5. Which third-party dependencies are managed by Boot's BOM?
6. Which versions are built and tested in CI?

A Boot major line can entail major shifts in Java baseline, Spring Framework, and the Jakarta namespace. For example, Boot 3 applications use Java 17+ and the Spring Framework 6/Jakarta ecosystem; you cannot take a module built for Boot 2/Framework 5 and assume compatibility just because class names match.

Do not pick versions merely by browsing version numbers on Maven Central. Read the system requirements, upgrade guides, and release notes for the exact Boot line.

### 3.2. Use the BOM Version Matching the Spring Boot Release

With this illustrative baseline:

~~~text
Spring Boot release: 3.3.13
BOM: org.springframework.boot:spring-boot-dependencies:3.3.13
Maven plugin: org.springframework.boot:spring-boot-maven-plugin:3.3.13
Gradle plugin: org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.13
~~~

Boot modules such as `spring-boot`, `spring-boot-autoconfigure`, and `spring-boot-starter` should share the release line and patch version managed by the BOM. Do not mix arbitrarily, for example:

~~~text
spring-boot                 3.3.13
spring-boot-autoconfigure   3.4.0
spring-boot-starter         3.2.12
~~~

Such a version mix can cause API, classpath, or runtime behavior mismatches. If you want to upgrade an individual Spring Boot module, first have a verified compatibility reason—do not apply random overrides to work around a poorly understood error.

### 3.3. The Acme Library Version Need Not Match the Spring Boot Version

Suppose a provider has:

~~~text
com.acme:acme-report-core:1.4.0
com.acme:acme-spring-boot-autoconfigure:1.4.0
com.acme:acme-spring-boot-starter:1.4.0
com.acme:acme-spring-boot-bom:1.4.0
~~~

Version `1.4.0` is the Acme library's version. It is not the Spring Boot version. The Acme BOM can declare that Acme release 1.4.0 was tested against Spring Boot 3.3.x, e.g., 3.3.13.

A library may adopt one of these policies:

- **One library release per Boot line:** easy to control the dependency baseline; bump release when switching Boot lines.
- **One library release supporting multiple Boot lines:** only claim this if CI truly builds/tests against each line and API/bytecode are compatible.
- **Separate BOMs per Boot line:** useful when dependencies or modules require different versions per Boot line.

The key is to **publish a clear compatibility matrix**. Do not leave users guessing from Acme versions happening to look similar to Boot versions.

## 4. Maven: Inherit spring-boot-starter-parent or Import the BOM?

Maven has two common ways to adopt Spring Boot's dependency management.

### 4.1. Approach A — Inherit spring-boot-starter-parent

This is the simple approach for a typical Spring Boot application:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>sample-application</artifactId>
    <version>1.0.0</version>

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
~~~

This parent provides many useful defaults beyond dependency management, including plugin management and Maven build settings following Spring Boot conventions. Thus the application can declare managed dependencies without specifying versions on each line.

### 4.2. Approach B — Import the spring-boot-dependencies BOM

If an organization already has its own parent POM or does not want to inherit from the Spring Boot parent, it can import the BOM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>sample-application</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>\${spring-boot.version}</version>
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
                <version>\${spring-boot.version}</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Here, the BOM manages dependency versions yet **does not supply all the build configuration provided by the parent POM**. When not using `spring-boot-starter-parent`, the project must manage plugin versions, compiler settings, encoding, and other Maven settings it needs itself.

### 4.3. Comparing the Two Approaches

| Criterion | Inherit Spring Boot parent | Import Spring Boot BOM |
| --- | --- | --- |
| Dependency version management | Yes | Yes |
| Boot's default plugin management | Yes | Not inherited automatically |
| Easy to use with company parent POM | Cannot have two direct parents | Suitable |
| Customizing Maven build | Inherit then override as needed | More explicit self-control |
| Suitable for | Simple applications needing no other parent | Organizations with own parent, libraries, or multi-module builds |

**Do not declare the Spring Boot BOM as a regular runtime dependency.** A BOM is imported inside `dependencyManagement` with `type=pom` and `scope=import`.

### 4.4. Managed Versions Can Be Overridden

For example, the BOM manages Jackson yet the project specifies its own version:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

A directly declared version can override the BOM version. This is an intentional action that requires compatibility testing. Do not override versions solely to make the dependency tree look newer; Spring Boot releases are tested against a specific dependency set.

## 5. Designing a Custom Starter and Custom BOM

A custom starter is often split into modules to clearly manage auto-configuration code, runtime libraries, and dependencies needed by applications.

### 5.1. Suggested Module Structure

~~~text
acme-report/
├── acme-report-core/
│   └── Business API and implementation
├── acme-spring-boot-autoconfigure/
│   ├── @AutoConfiguration
│   ├── @ConfigurationProperties
│   └── AutoConfiguration.imports
├── acme-spring-boot-starter/
│   └── dependency descriptor for users
└── acme-spring-boot-bom/
    └── BOM managing versions of Acme and Boot modules
~~~

Roles:

- **core:** contains API/implementation that does not necessarily depend on Spring Boot.
- **autoconfigure:** contains auto-configuration classes, properties, and Spring Boot integration.
- **starter:** bundles needed dependencies so users only need to add a single dependency.
- **bom:** manages versions of Acme modules and, if policy requires, imports the compatible Spring Boot BOM.

Spring Boot recommends that third-party starters do not use names starting with `spring-boot`; name them after the product, e.g., `acme-spring-boot-starter`. The auto-configuration and starter modules can be kept separate or combined if the feature is simple enough.

### 5.2. Autoconfigure Module Using Boot BOM to Align Dependencies

Part of the auto-configuration module's POM might look like:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <acme.version>1.4.0</acme.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>\${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-report-core</artifactId>
        <version>\${acme.version}</version>
    </dependency>
</dependencies>
~~~

The POM above shows the key dependencies section, which can live in a separate Maven module. The Boot BOM manages the `spring-boot-autoconfigure` version; Acme core's version is managed by Acme's release.

If auto-configuration integrates with an optional third-party library, consider declaring that dependency optional and adding a classpath condition. The starter then decides whether to include that optional dependency in the default bundle.

### 5.3. Starter Module Bundles Only Necessary Dependencies

Abbreviated starter POM:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-report-core</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

This is a structural example. In real projects, an internal parent/BOM can manage Acme module versions instead of repeating `1.4.0`. The starter should contain dependencies needed for common use cases; do not include every optional integration merely because it might be useful.

### 5.4. Creating a Dedicated BOM for Acme Artifacts

Acme's BOM helps applications consume modules from the same release:

**acme-spring-boot-bom/pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-bom</artifactId>
    <version>1.4.0</version>
    <packaging>pom</packaging>

    <properties>
        <spring-boot.version>3.3.13</spring-boot.version>
        <acme.version>1.4.0</acme.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>\${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-report-core</artifactId>
                <version>\${acme.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-spring-boot-autoconfigure</artifactId>
                <version>\${acme.version}</version>
            </dependency>

            <dependency>
                <groupId>com.acme</groupId>
                <artifactId>acme-spring-boot-starter</artifactId>
                <version>\${acme.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

This BOM manages Acme module versions and also imports Spring Boot BOM 3.3.13. Thus it **intentionally ties Acme BOM release 1.4.0 to Boot 3.3.13/3.3.x**. When importing this BOM, consumers get a coordinated set of versions for the artifacts managed by the BOM.

If Acme wants to support another Boot line with a different dependency baseline, publish a corresponding BOM or compatibility configuration and test separately. Do not alter the Boot version inside an old BOM without re-evaluating the entire dependency graph.

### 5.5. Application Consuming the Custom BOM

In the application's POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-bom</artifactId>
            <version>1.4.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The application does not have to repeat the version for the starter. The Acme BOM manages Acme module versions and, in this example, provides dependency management from the imported Boot BOM.

**Note on Maven:** dependency management does not propagate endlessly across every dependency graph. When an application imports a BOM, it receives dependency management from that BOM via the import mechanism. When a library only uses a BOM in its own build, do not assume every consuming application will automatically inherit the library's entire dependency management. Inspect the published POM and consumer dependency graph; if you want to provide a version set to consumers, intentionally publish a BOM and document how to import it.

## 6. Gradle: Using a BOM With platform

Gradle supports BOMs via `platform()` and `enforcedPlatform()`. Spring Boot can also use the `io.spring.dependency-management` plugin.

### 6.1. Approach A — Spring Dependency Management Plugin

When using the Spring Boot Gradle plugin together with the dependency management plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When the dependency management plugin is applied, the Spring Boot Gradle plugin automatically imports the `spring-boot-dependencies` BOM matching the plugin's version. Therefore versions can be omitted on managed dependencies.

This approach feels familiar to Maven users because it allows customizing versions via properties supported by the BOM, depending on plugin and configuration.

### 6.2. Approach B — Gradle Native BOM Support

Gradle can also use platforms directly:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

With this approach, `platform(...)` imports constraints from the BOM into the relevant configuration. This is Gradle's native option, requiring no dependency management plugin to read the BOM.

### 6.3. How platform and enforcedPlatform Differ

| Declaration | Meaning |
| --- | --- |
| `platform("...")` | Introduces version constraints from the BOM into dependency resolution; Gradle still considers other constraints in the graph |
| `enforcedPlatform("...")` | Forces versions from the BOM as strict requirements, overriding other versions in the graph |

Example:

~~~groovy
dependencies {
    implementation enforcedPlatform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

Use `enforcedPlatform` when you genuinely want to force the entire graph to follow the BOM's versions and understand the impact on other dependencies. For libraries published for multiple applications to consume, propagating enforced constraints can restrict applications' ability to choose versions. Usually consider `platform` first; only use `enforcedPlatform` for intentional version-control policies.

### 6.4. Version Catalogs Do Not Replace a BOM

A Gradle version catalog (`libs.versions.toml`) centralizes dependency coordinates and aliases. It is a declaration management tool, whereas a platform/BOM participates in dependency resolution to supply version constraints.

You can use a catalog alongside a BOM:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-web = { module = "org.springframework.boot:spring-boot-starter-web" }
~~~

~~~groovy
dependencies {
    implementation platform(libs.spring.boot.bom)
    implementation libs.spring.boot.web
}
~~~

The catalog keeps dependency names consistent; the BOM coordinates versions. The two tools complement each other.

## 7. Managing Versions Across Multiple Modules and Release Lines

### 7.1. Do Not Let Individual Modules Pick Boot Versions Independently

A multi-module project might look like:

~~~text
acme-report-parent
  ├── acme-report-core
  ├── acme-spring-boot-autoconfigure
  ├── acme-spring-boot-starter
  └── acme-spring-boot-bom
~~~

Manage versions in one place:

- Internal Acme versions use a property or parent/BOM.
- Spring Boot version uses a single consistent property for the build line under test.
- Spring Framework versions come from the Boot BOM.
- Maven/Gradle plugins match the chosen release line.
- Annotation processors and test dependencies are also aligned to the same release line.

Avoid letting the core module use one Spring Boot version, the auto-config module another, and the test module a third.

### 7.2. Release Policy by Boot Line

A compatibility matrix should be published alongside the library:

| Acme library/BOM | Tested Spring Boot line | Java baseline | Notes |
| --- | --- | --- | --- |
| `1.4.x` | `3.3.x` | 17+ | Policy example for BOM 1.4.0 |
| `1.5.x` | `3.4.x` | 17+ | Example of a subsequent release line, published only after CI verification |
| `2.x` | New Boot major | Per the Boot line's system requirements | May require API or namespace changes |

The rows above are **examples of how to organize a matrix**, not claims about a real Acme product. When releasing, substitute versions that have actually been tested and committed for support.

You can choose among these versioning policies:

**One library version, multiple Boot lines:** suitable when source/API are compatible and CI tests every line. Consumers still must pick the Boot BOM matching their application.

**One BOM per Boot line:** useful when dependency management or module variants differ. BOM versions can be set independently while clearly stating which Boot release each imports.

**Splitting library major versions:** suitable when dropping an old Boot line, raising the Java baseline, or making incompatible API/namespace changes. You do not necessarily have to bump major just because a Boot patch increases; base the decision on the library's compatibility contract.

### 7.3. Do Not Use Version Ranges or Dynamic Versions for Production Starters

Avoid declarations like:

~~~xml
<version>[3.3,4.0)</version>
~~~

or in Gradle:

~~~groovy
implementation 'org.springframework.boot:spring-boot-autoconfigure:3.+'
~~~

Version ranges/dynamic versions can cause builds today and tomorrow to resolve to different results. They reduce reproducibility and make compatibility bugs hard to investigate.

For production builds/releases, use concrete versions or a concrete BOM. When adopting a new patch release, bump the BOM intentionally, run CI, and re-release.

## 8. Which Dependencies Should the Boot BOM Manage?

### 8.1. Spring Boot and Spring Framework

Do not manually specify versions for Spring Boot/Spring Framework modules already managed by the Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>
~~~

Do not manually pin custom versions for `spring-core`, `spring-beans`, `spring-web`, or `spring-webmvc` in a typical Boot application. Spring Framework modules have compatibility ties to the Boot release.

### 8.2. Third-Party Libraries

The Boot BOM also manages many third-party libraries such as JSON, logging, database drivers, and test libraries. Use the BOM version whenever a dependency is in the managed list.

If a dependency is not managed by the Boot BOM:

1. Identify the provider's own BOM if available.
2. Check that library's compatibility matrix.
3. Choose a version tested alongside the Boot line.
4. Manage the version in the organization's custom BOM if multiple modules share it.

Do not assume the Boot BOM covers every dependency on Maven Central.

### 8.3. Spring Cloud and Related Release Trains

If the starter integrates Spring Cloud, Spring Data, or an ecosystem with its own BOM, consult that ecosystem's own compatibility matrix. For example, Spring Cloud maps its release trains to specific Spring Boot lines. Do not pick the latest release train independently of the Boot version in use.

When using multiple BOMs:

- Document which BOM manages which group of artifacts.
- Avoid having two BOMs manage the same artifact with conflicting versions without a clear rule.
- Inspect the effective POM/dependency insight after importing.
- Only override a version when there is a reason, an owner, and verifying tests.

## 9. Inspecting the Dependency Graph After Importing a BOM

A BOM only adds value when the final resolution matches expectations.

### 9.1. Maven

Inspect the dependency tree:

~~~bash
mvn dependency:tree
~~~

Inspect only Spring modules:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot,org.springframework
~~~

Inspect the effective POM:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Check:

- Are there multiple versions of the same artifact?
- Do Spring Boot module versions share the same patch?
- Do Spring Framework modules match the release line managed by the Boot BOM?
- Which versions were omitted for conflict and why?
- Did any dependency directly declare a version overriding the BOM?
- Did another starter pull in an unintended dependency?

### 9.2. Gradle

Inspect the runtime dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect why a version was chosen:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Check Spring Framework:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

`dependencyInsight` shows which dependencies requested a version, which constraints participated in resolution, and why Gradle selected the final version.

### 9.3. Maven Enforcer to Catch Dependency Convergence Issues

You can add a convergence rule to the Maven build:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.5.0</version>
            <executions>
                <execution>
                    <id>check-dependency-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This rule detects cases where multiple dependency paths request different versions of the same artifact. It does not automatically resolve every conflict and sometimes requires intentional exceptions. When a build fails, read the dependency paths before adding exclusions or overrides.

## 10. Testing Compatibility in CI

A library should only claim support for Boot lines it has tested. A CI pipeline can:

1. Build core and auto-config against the minimum Java baseline.
2. Run unit tests for properties, conditions, and bean back-off.
3. Run integration tests against the supported Spring Boot line.
4. Check the dependency graph and convergence.
5. Build/publish the starter POM to a local repository or staging repository.
6. Create a small consumer application declaring only the starter, verifying auto-configuration is discovered and runs.
7. Repeat for every Boot line in the compatibility matrix.

If using Maven to import the BOM via a property:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>
~~~

CI can pass the selected version:

~~~bash
mvn -Dspring-boot.version=3.3.13 clean verify
~~~

When testing another line, pass the matching BOM version and rerun the full test suite. Do not swap dependency versions in one step while skipping consumer tests.

With Gradle, you can create matrix jobs driven by version catalog/property or build parameters. What matters is that each job actually resolves that line's BOM; merely renaming a job without changing dependency constraints does not create a new compatibility test.

### 10.1. Inspecting the Published POM

For a custom starter, testing source modules alone is not enough. Inspect the published artifacts:

- Does the starter POM declare the right dependencies?
- Are dependency versions resolved properly in consumers?
- Are optional dependencies pulled in unintentionally?
- Does the custom BOM properly manage versions of Acme modules?
- Did the BOM accidentally import the wrong Boot line?
- Can an application that only imports the BOM and declares the starter build cleanly?

The published POM is part of the library's distribution API. A module compiling inside a reactor does not prove an independent consumer can resolve dependencies properly.

## 11. A Complete Release Strategy Example

Suppose Acme publishes a reporting library suite:

~~~text
acme-report-core                  1.4.0
acme-spring-boot-autoconfigure    1.4.0
acme-spring-boot-starter          1.4.0
acme-spring-boot-bom              1.4.0
Spring Boot baseline              3.3.13
Java baseline                     17
~~~

Policy:

- All Acme modules share release 1.4.0.
- Custom BOM 1.4.0 imports `spring-boot-dependencies:3.3.13`.
- The auto-config module uses `spring-boot-autoconfigure` from the Boot BOM.
- The starter bundles core + auto-config + minimal dependencies.
- Consuming applications import the Acme BOM and declare the starter without a version.
- CI tests on Java 17 with Boot 3.3.13 and additional patches in that line if the organization commits to supporting them.
- To support Boot 3.4, create a separate test matrix; reuse Acme 1.4.0 only if API and dependencies are genuinely compatible. If a different dependency baseline is needed, publish an appropriate BOM/library variant.
- When upgrading a Boot patch, bump the BOM, inspect the dependency tree, run CI, and re-release following the workflow.

This separates versioning concerns:

~~~text
Acme release version       -> version of the Acme library
Spring Boot BOM version    -> Boot release the dependency set is compatible with
Java baseline              -> minimum supported runtime/compiler
Compatibility matrix       -> tested/committed combinations
~~~

Do not force the Acme version to equal the Boot version. What must align is the published and verified compatibility contract.

## 12. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Starter pulls multiple Spring Boot versions | Modules declare differing versions or BOM not imported properly | Align onto one Boot BOM and inspect dependency tree |
| Spring Framework version diverges from Boot | Manual override of spring-core/spring-context | Remove manual version and let Boot BOM manage it |
| Imported BOM yet dependency missing from classpath | Confused dependencyManagement with dependencies | Declare the actual dependency inside dependencies |
| Not using Boot parent so plugins lack versions | BOM does not manage Maven plugins | Declare plugin version/configuration explicitly |
| Custom starter builds yet consumer fails resolution | Published POM missing or has wrong dependency/version management | Test from an independent consumer project and inspect POM |
| Acme BOM pulls an incompatible Boot line | BOM published with unclear mapping | Tie BOM to a Boot line, publish matrix, and test |
| Using enforcedPlatform prevents other apps from upgrading libraries | Strict constraint enforced from dependency | Use `platform` where appropriate; only enforce under clear policy |
| Version ranges make builds non-reproducible | Resolver picks different versions over time | Pin concrete BOM/releases |
| Importing multiple BOMs yields unexpected versions | Multiple BOMs manage the same artifact | Inspect effective POM/dependencyInsight and assign ownership |
| Spring Cloud incompatible with Boot | Picked release train independently | Follow the Spring Cloud compatibility matrix |
| Only tested autoconfigure module, not starter | Distribution artifact unverified | Create a consumer smoke test against published starter |

## 13. Pre-Release Checklist for a Custom Starter

### Version policy

- [ ] Identify supported Boot major/minor lines.
- [ ] Identify Java baseline and Spring Framework generation.
- [ ] Use the Boot BOM matching the Boot plugin release.
- [ ] Let the BOM manage Spring Boot/Spring Framework modules.
- [ ] Do not use version ranges or dynamic versions in production releases.
- [ ] Publish Acme version and Boot compatibility matrix.

### Maven/Gradle

- [ ] Distinguish parent POM, imported BOM, and actual dependencies.
- [ ] Custom BOM manages versions of internal modules.
- [ ] If custom BOM imports Boot BOM, state clearly which Boot line it binds to.
- [ ] Gradle `platform`/`enforcedPlatform` chosen intentionally.
- [ ] Plugin versions managed explicitly, especially when not using Boot parent.

### Verification

- [ ] Inspect Maven dependency tree/effective POM or Gradle `dependencyInsight`.
- [ ] Check dependency convergence.
- [ ] Build and test on every published Boot line.
- [ ] Test the starter artifact from an independent consumer.
- [ ] Inspect published POM/BOM and dependency scopes/optional flags.
- [ ] Document exact tested versions in release notes.

## 14. Self-Check Questions

**Question 1.** How does a BOM differ from `dependencies`?  
**Answer:** A BOM provides dependency management/version constraints; `dependencies` is what puts artifacts onto the classpath.

**Question 2.** Why should you use `spring-boot-dependencies` matching the running Spring Boot release?  
**Answer:** Each Boot release has a curated and tested set of dependencies. Using the matching BOM keeps Spring Boot, Spring Framework, and third-party libraries on a compatible version set.

**Question 3.** Are inheriting `spring-boot-starter-parent` and importing `spring-boot-dependencies` identical?  
**Answer:** No. Both supply dependency management, yet the parent also provides plugin management and many build defaults; importing the BOM only imports dependency management.

**Question 4.** Can a custom BOM manage Acme module versions and import the Boot BOM?  
**Answer:** Yes. That is a way to give consumers a unified version set; clearly publish which Boot line the Acme BOM is compatible with.

**Question 5.** Must Acme version 1.4.0 necessarily use Spring Boot 1.4.0?  
**Answer:** No. The two versions belong to different products/release trains. Acme must publish a compatibility matrix rather than relying on matching version numbers.

**Question 6.** Why does `enforcedPlatform` require caution when publishing Gradle libraries?  
**Answer:** It imposes strict version constraints onto consumers' dependency graphs, potentially preventing applications from choosing versions compatible with their own ecosystem.

**Question 7.** How do you verify final resolved versions after importing a BOM?  
**Answer:** Maven uses `dependency:tree` and `help:effective-pom`; Gradle uses `dependencies` and `dependencyInsight`.

**Question 8.** Is a successful build of the auto-config module alone enough to prove a custom starter is ready for release?  
**Answer:** No. You must inspect the published POM/BOM and build an independent consumer using only the starter.

## 15. Official References

- [Spring Boot 3.3 — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html)
- [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Gradle — Platforms and BOM Support](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)

**Takeaway:** Choose the **compatible Spring Boot release line first**, import the matching release BOM, let the BOM manage Spring modules and related dependencies, and manage your library's own versions in a custom BOM. Parent POM, BOM, and dependencies carry distinct responsibilities; Gradle `platform` and `enforcedPlatform` also enforce different constraint strengths. Finally, inspect the dependency graph and run CI across every Boot/Java combination the library commits to supporting.
