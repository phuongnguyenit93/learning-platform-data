# Distinguishing Boot Plugin Upgrades from BOM and Application Dependency Upgrades

## Objectives

When upgrading Spring Boot, three distinct changes are often lumped together as "upgrading the Boot version":

1. **Upgrading the build plugin:** changing the Gradle or Maven plugin that runs during the build, packaging, and creation of the executable artifact.
2. **Upgrading the BOM (Bill of Materials):** changing the set of dependency versions managed by Spring Boot, such as Spring Framework, Jackson, Hibernate, and logging.
3. **Upgrading application dependencies:** adding, removing, or changing a specific library directly used by business code.

These three actions are related, yet they affect different parts of the build. If you change the wrong version in the wrong place, the project may build while the runtime uses an incompatible set of libraries, or the `bootJar`/`repackage` task may not run as expected.

This guide uses **Spring Boot 3.3.13** as a fixed example baseline based on that release's documentation. This is not a claim that 3.3.13 is the latest release. When upgrading a real project, pick a still-supported release and read the system requirements, release notes, and migration guide of the target release.

After this guide, you will be able to distinguish the three version types, select a BOM strategy for Gradle/Maven, find the actually resolved dependency versions, and upgrade via a verifiable process.

---

## 1. Four Version Layers in a Spring Boot Project

| Layer | Example | Role |
| --- | --- | --- |
| Build tool and JDK | Gradle Wrapper, Maven Wrapper, JDK 17 | Runs the build, compiles, and controls bytecode |
| Spring Boot build plugin | `org.springframework.boot` Gradle plugin or `spring-boot-maven-plugin` | Provides tasks and packaging behavior |
| Dependency platform/BOM | `spring-boot-dependencies` | Manages application and transitive dependency versions |
| Application dependencies | `spring-boot-starter-web`, SDK, JDBC driver | Determines which libraries are actually on the classpath |

Example configuration:

~~~text
JDK:                         17
Gradle Wrapper:              8.x
Spring Boot Gradle plugin:   3.3.13
Spring Boot BOM:             3.3.13
Application dependency:     spring-boot-starter-web
Internal SDK:                4.2.0
~~~

The `org.springframework.boot` plugin lives in build logic; `spring-boot-dependencies` is the platform managing dependencies; starters and SDKs live in the application's dependency graph.

### 1.1 Build Plugin

The plugin is declared in the Gradle `plugins` block or Maven `build/plugins`. It runs during the build and can:

- Register tasks to create executable archives, such as Gradle `bootJar`.
- Configure tasks to run the application, such as `bootRun`.
- Integrate with Java, Kotlin, War, or other build plugins.
- Configure executable JAR/WAR and Maven `repackage`.
- Provide image-building or build-information tasks when the corresponding features are enabled.

The plugin is not a dependency imported by application code in `src/main/java`. Do not add `spring-boot-gradle-plugin` to `implementation` just to upgrade the build plugin.

### 1.2 BOM

A BOM is a POM with `dependencyManagement` describing managed versions for a set of modules. Spring Boot publishes a BOM with coordinates:

~~~text
org.springframework.boot:spring-boot-dependencies:3.3.13
~~~

When the BOM is in effect, managed dependencies can be declared without writing a version on each line:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

A BOM does not automatically create the `bootJar` task, does not package the application, and does not automatically add every dependency to the project. The application must still declare the starters/libraries it actually uses.

### 1.3 Application Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    implementation 'com.acme:partner-sdk:4.2.0'
}
~~~

These lines add modules to the dependency graph. The BOM can manage the versions of some modules; dependencies not in the BOM may need their own version. Upgrading an application dependency does not mean you must upgrade the Spring Boot plugin.

### 1.4 Plugin and BOM Can Be Linked

This is an important point when using Gradle:

- When the Spring Boot Gradle plugin is used together with `io.spring.dependency-management`, the plugin automatically imports `spring-boot-dependencies` matching **the Spring Boot plugin version in use**.
- When using Gradle native BOM support, the project declares `platform("org.springframework.boot:spring-boot-dependencies:...")` in `dependencies`. The BOM version is explicitly written in the dependency declaration.
- Both strategies are valid. Choose one clear management approach and inspect the actually resolved versions.

Therefore, in a Gradle setup using the `dependency-management` plugin, changing the Spring Boot plugin version usually changes the automatically imported BOM at the same time. Do not assume that upgrading only the plugin will always keep the same set of dependencies.

---

## 2. Upgrading the Spring Boot Gradle Plugin

### 2.1 Declaring the Plugin

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}
~~~

`org.springframework.boot` is the plugin ID. `3.3.13` here is the version of the **Gradle plugin**, resolved by Gradle from plugin repositories. It is not a runtime dependency loaded by the JVM when the application starts.

When the plugin is applied alongside the Java plugin, Spring Boot can configure the executable JAR task and related tasks. If the plugin is not applied properly, the `bootJar` task may not exist even if the project declares Spring Boot libraries.

### 2.2 Plugin Repositories Differ from Dependency Repositories

The Gradle `plugins` block uses the plugin resolution mechanism. Repositories are typically configured in `pluginManagement` inside `settings.gradle`:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

If the organization uses an internal plugin repository, add that endpoint according to organizational policy. Do not confuse `pluginManagement.repositories` with the `repositories` used to download application dependencies.

### 2.3 Centralized Plugin Version Management

In a multi-project build, the root can declare the version with `apply false`:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
~~~

The application module then applies the plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

Only apply the Boot plugin to modules that are actually Boot applications. A plain Java library module usually does not need this plugin.

The plugin version can also be stored in `gradle/libs.versions.toml`:

~~~toml
[versions]
springBoot = "3.3.13"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
~~~

A version catalog centralizes aliases/versions, but it does not by itself replace a BOM. Plugin aliases only manage build plugins; managing transitive dependencies still requires a BOM/platform or dependency constraints.

---

## 3. Two Strategies for Using the Spring Boot BOM in Gradle

### 3.1 Approach A — dependency-management Plugin

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

apply plugin: 'io.spring.dependency-management'

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When `io.spring.dependency-management` is applied, the Spring Boot Gradle plugin automatically imports the `spring-boot-dependencies` BOM matching the Boot plugin version. Dependencies managed by the BOM can omit the version in their declaration.

The Spring Boot plugin brings the `dependency-management` plugin dependency on the build plugin classpath; therefore, you can apply the plugin by ID as in the example above without necessarily declaring a separate version for it.

**Upgrade consequence:** if you change the Boot Gradle plugin from 3.3.13 to another release and continue using automatic import, the default BOM also switches to the new plugin version. Review the dependency graph at the same time.

The `dependency-management` plugin lets you customize version properties published by the BOM. Structural example:

~~~groovy
ext['slf4j.version'] = '2.0.16'
~~~

Property names and versions must be confirmed in the dependency version properties table of the exact Spring Boot release. Do not guess property names or copy properties from another release. Overrides can skew the dependency set away from what Boot tested; only do this when specifically required and backed by tests.

### 3.2 Approach B — Gradle Native BOM Support

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

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

In this approach, the BOM version is explicitly declared in `platform(...)`. The Boot Gradle plugin still provides tasks/packaging; `platform(...)` manages application dependency versions.

Spring Boot notes that native BOM support can make builds faster. In return, customizing versions via BOM Maven properties is not supported the same way as with the `dependency-management` plugin; use Gradle dependency constraints or version resolution mechanisms instead.

### 3.3 platform and enforcedPlatform

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

~~~groovy
dependencies {
    implementation enforcedPlatform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

| Declaration | Meaning |
| --- | --- |
| `platform(...)` | Uses BOM constraints during version resolution; other constraints/versions in the dependency graph can still influence the result |
| `enforcedPlatform(...)` | Applies versions from the platform as mandatory requirements, overriding other versions in the graph |

Do not choose `enforcedPlatform` just to make build conflicts disappear. It can force versions onto transitive dependencies with which another library is incompatible. Start with `platform` and only use enforced behavior once you understand the scope of impact.

### 3.4 Do Not Accidentally Import the BOM Twice

If you have applied the `dependency-management` plugin and the Boot plugin automatically imports the BOM, you generally do not need to add a `platform` for the same BOM to `dependencies`.

If you have chosen native BOM support, do not also apply the `dependency-management` plugin and re-import the BOM unless there is an explicit design for it. Having both mechanisms participate in version management makes it harder for readers to tell where the final version came from.

### 3.5 Which Strategy Should You Choose?

| Need | Recommendation |
| --- | --- |
| Existing project uses `dependency-management` plugin stably | Continue the current approach when upgrading Boot |
| Want to use Gradle native BOM support | Use `platform(...)`, inspect constraints and version resolution |
| Need to customize BOM properties published by Spring Boot | `dependency-management` plugin is more convenient |
| Want BOM version explicitly written, decoupled from Boot plugin version | Native `platform(...)` makes this relationship transparent |
| Multiple modules need a shared version policy | Consider a convention plugin or internal platform |

There is no single right strategy for every repository. What matters is identifying the source of versions, applying it consistently, and being able to explain why Gradle resolved the final versions.

---

## 4. Maven: Parent POM and BOM Import Are Not the Same

### 4.1 Using spring-boot-starter-parent

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

<groupId>com.example</groupId>
<artifactId>orders-service</artifactId>
<version>1.0.0</version>

<properties>
    <java.version>17</java.version>
</properties>
~~~

The parent provides dependency management and plugin defaults:

- Dependency management inherited from `spring-boot-dependencies`.
- Plugin management for related build plugins.
- Maven compiler/resource configuration and other defaults.
- The `repackage` execution of the Spring Boot Maven plugin per parent configuration.

When upgrading the parent version, review both the dependency management and plugin management provided by the parent.

### 4.2 Importing spring-boot-dependencies Separately

If the project cannot inherit from `spring-boot-starter-parent` because it already has a corporate parent, you can import the BOM:

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

This provides Spring Boot's dependency management but **does not bring along the starter parent's plugin management**. If you need an executable JAR, you must configure the appropriate `spring-boot-maven-plugin` in `build/plugins`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.13</version>
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

The Maven plugin version is the build plugin version. The version in the BOM is the dependency platform version. These two lines can be managed independently when not using the starter parent.

### 4.3 Comparing Parent and BOM Import

| Capability | `spring-boot-starter-parent` | Importing `spring-boot-dependencies` |
| --- | --- | --- |
| Manages dependency versions | Yes | Yes |
| Plugin management | Yes | No |
| Default `repackage` configuration | Has execution from parent | Needs plugin/execution declared if desired |
| Used when already having a corporate parent | Cannot inherit two parents directly | More suitable |
| Where the Boot version lives | Parent version | BOM version; plugin version configured separately |

Maven only allows one direct parent. If the organization has its own parent, importing the BOM is a common way to get Spring Boot's dependency management while keeping the corporate parent.

### 4.4 Directly Declared Versions Can Override the BOM

The BOM manages versions when a dependency does not declare its own version. If the application declares a direct version for `jackson-databind` or another module, that version can override the managed version. Only do this when there is a compatibility/security rationale and it has been tested.

The parent/BOM may publish properties controlling the versions of certain dependencies. When the exact property is supported, it can be overridden in the project:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

Illustrative property names and values must be cross-checked against the dependency version properties table of the specific release. When importing only the BOM without using the starter parent, property override mechanics differ from inheriting the parent; you must declare an appropriate `dependencyManagement` entry or use another version management mechanism.

---

## 5. Upgrading Application Dependencies Without Upgrading the Boot Plugin

### 5.1 Adding a BOM-Managed Starter

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

If the BOM manages the starter, no separate version is needed. This is an application feature change.

### 5.2 Upgrading a Library Not in the BOM

~~~groovy
dependencies {
    implementation 'com.acme:partner-sdk:4.2.0'
}
~~~

When upgrading the SDK to 4.3.0, change the version in the declaration or version catalog. There is no need to change the Boot plugin unless there are other compatibility requirements.

### 5.3 Upgrading a Dependency Already Managed by the BOM

There are three situations:

1. A newer BOM release already upgrades the dependency: upgrade the BOM along with the appropriate Boot release.
2. A security fix is needed before upgrading Boot: override the dependency version in a controlled way, using the appropriate property/constraint/dependency-management policy.
3. The dependency is not in the BOM: manage the version in the application or organizational platform.

Do not manually add versions to every dependency just to "pin to be safe." Doing so prevents the project from receiving compatible updates from the BOM on the next upgrade.

### 5.4 Direct Dependencies vs. Transitive Dependencies

The version written in a declaration is not always the final version of every transitive dependency. Distinguish:

- Direct dependency: a module declared by the application.
- Transitive dependency: a module pulled in by a direct dependency.
- Constraint/BOM: rules participating in version selection.
- Resolved version: the final version actually chosen by the build tool.

For example, `spring-boot-starter-web` pulls in many Spring/Jackson modules. To know final versions, inspect the runtime dependency graph instead of inferring them from the starter name.

---

## 6. Safe Upgrade Process

### Step 1 — Establish a Baseline

Record current versions:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
~~~

With Maven:

~~~bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree -Dscope=runtime
~~~

Record the Boot plugin, BOM, Java, Gradle/Maven Wrapper, direct dependencies with version overrides, and dependency constraints. Do not save only `build.gradle`; save the resolved dependency graph because actual versions can differ from declared versions.

### Step 2 — Choose Target Boot Release and Check Compatibility

For the Spring Boot 3.3.13 example, the documentation states:

| Component | Requirement/Compatibility |
| --- | --- |
| Java | Minimum Java 17; compatible up to Java 23 |
| Spring Framework | 6.1.21 and later |
| Gradle | Gradle 7.x (7.5 or later) and 8.x |
| Maven | 3.6.3 or later |

Do not extrapolate this table to all Boot 3.x or Boot 4.x releases. Each release line has its own limits. Third-party plugins, annotation processors, or native tools may require newer versions.

### Step 3 — Identify the Dependency Management Strategy

Answer clearly:

- Is Gradle using `io.spring.dependency-management` or native `platform`?
- If using the `dependency-management` plugin, does the BOM automatically follow the Boot plugin version?
- If using native BOM, in which file is the platform version declared?
- Is Maven using the starter parent or importing the BOM separately?
- Is any corporate platform/parent adding constraints?

Only edit versions after answering these questions.

### Step 4 — Upgrade the Plugin and BOM in the Right Place

- Gradle `dependency-management` strategy: upgrade the Boot plugin and inspect the auto-imported BOM.
- Gradle native BOM strategy: update the plugin and platform version per the target release.
- Maven starter parent: upgrade the parent version and review plugin/dependency management.
- Maven BOM import: upgrade the BOM version; update the Maven plugin version separately if needed.

Do not change multiple version management mechanisms in the same step if unnecessary. If you want to migrate from the `dependency-management` plugin to native BOM, isolate that into a separate tested change to make comparing dependency graphs easier.

### Step 5 — Inspect the Dependency Diff

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
./mvnw help:effective-pom
~~~

Check the selected versions, the dependency paths pulling them in, and the selection reasons. Pay particular attention to direct version overrides that skew away from the BOM.

### Step 6 — Upgrade Application Dependencies Separately

After the Boot plugin/BOM stabilizes:

- Add/remove starters per features.
- Upgrade SDKs not managed by the BOM.
- Review mandatory dependency overrides.
- Remove unnecessary version declarations if managed by the BOM and permitted by policy.
- Check dependency scopes: `implementation`, `runtimeOnly`, `compileOnly`, Maven `provided`, `runtime`, and `test`.

### Step 7 — Handle API/Configuration Changes

Compile errors after upgrading the BOM can come from Spring Framework, Jackson, Hibernate, or other libraries. Read the migration guide and release notes for the relevant dependencies. Do not immediately downgrade the BOM over a compile error if the error stems from a changed API with a supported migration path.

### Step 8 — Verify the Executable Artifact

Gradle:

~~~bash
./gradlew clean check bootJar
java -jar build/libs/orders-service-1.0.0.jar
~~~

Maven:

~~~bash
./mvnw clean verify
java -jar target/orders-service-1.0.0.jar
~~~

File names depend on project configuration and version. Use the actual output path. Verify application startup, health endpoint, DB connectivity, serialization, security filters, and critical flows.

### Step 9 — Verify the Container

If production runs containers, build the image from the exact tested executable artifact, record the image digest, and run a smoke test in the same base image/JRE. Promote the exact verified image digest, avoiding rebuilding a different artifact after testing.

---

## 7. Reading the Dependency Graph to Determine Final Versions

### 7.1 Gradle dependencies and dependencyInsight

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

If it is a single-project build, omit `:app:`. `dependencyInsight` shows which module requests the dependency, how many transitive paths exist, which version was selected, and why (conflict resolution, constraint, platform, force, or rule).

If you upgraded the BOM yet `spring-core` remains on an old version, check direct dependencies/constraints or other platforms participating in the graph.

### 7.2 Maven dependency:tree

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
~~~

`-Dverbose` helps reveal nodes omitted due to conflict mediation. Combine it with `help:effective-pom` to trace whether a version came from a parent, BOM, profile, or dependency declaration.

### 7.3 Build Files Are Inputs; the Dependency Graph Is the Result

If `pom.xml` imports BOM 3.3.13 but a direct dependency declares its own Jackson version, or Gradle uses a platform while another constraint requires a higher version, final versions must be determined from dependency resolution output.

Do not only look at versions in source files. When reviewing an upgrade, compare the dependency graph before and after.

---

## 8. Multi-Project Builds

A system may be structured as:

~~~text
platform/
├── settings.gradle
├── build.gradle
├── orders-service/
│   └── build.gradle
├── billing-service/
│   └── build.gradle
└── shared-library/
    └── build.gradle
~~~

Not every module needs the Spring Boot plugin. `orders-service` and `billing-service` are applications that can apply the plugin; `shared-library` may only need `java-library`.

### 8.1 Declaring the Plugin Version at the Root

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
~~~

Application module:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

This synchronizes the plugin version across application modules. Avoid applying the Boot plugin to every subproject if a module does not need Boot's tasks/packaging.

### 8.2 Managing the BOM in One Place

If using a native platform, you can create a convention plugin or shared platform dependency so application modules import the same BOM version. If using the `dependency-management` plugin, keep the BOM import strategy consistent and avoid having one module use the plugin while another imports a different BOM version without reason.

### 8.3 A Shared Library Does Not Necessarily Need the Boot BOM

A plain Java library may be consumed by multiple applications running different Boot releases. Consider whether the library should manage its own API dependencies with its own platform or let consumer applications manage versions through their BOMs.

Do not impose a Boot BOM on every module if that module does not depend on the Spring Boot ecosystem.

---

## 9. Signs You Upgraded the Wrong Layer

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `bootJar` does not exist | Boot plugin not applied or plugin resolution failed | `plugins`, plugin repositories, module build file |
| Starter reports missing version | BOM not imported into the active configuration | `dependency-management` plugin/platform and scope |
| Upgrading plugin changes many library versions | BOM automatically follows plugin version | `dependency-management` plugin and resolved graph |
| Upgrading BOM leaves build tasks unchanged | BOM only manages dependencies | Plugin version and plugin tasks |
| Maven has dependency versions but creates no executable JAR | Importing BOM does not configure Maven plugin/repackage | `spring-boot-maven-plugin` and execution |
| Maven parent upgrade changes compiler/plugin defaults | Parent manages both dependencies and plugin defaults | Effective POM and release notes |
| Dependency stays on old version after BOM upgrade | Explicit version/constraint/another platform | `dependencyInsight` or `dependency:tree` |
| An SDK has no version after removing its version | SDK is not managed by the BOM | Dependency declaration/catalog/platform |
| Runtime fails even though compile passes | Runtime graph differs from compile graph or wrong dependency scope | `runtimeClasspath`, archive contents |
| New Boot plugin yet Gradle is incompatible | Gradle Wrapper is too old | System requirements of the Boot release |

---

## 10. Common Configuration Mistakes

### 10.1 Putting the Gradle Plugin in dependencies

Wrong purpose:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-gradle-plugin:3.3.13'
}
~~~

This declares a library dependency in the application graph. It does not apply the Gradle plugin and does not create the `bootJar` task.

The correct way is to apply the plugin:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
}
~~~

### 10.2 Assuming Importing the BOM Adds Starters

Importing `spring-boot-dependencies` does not give an application Spring MVC. A BOM only manages versions; you must declare `spring-boot-starter-web` if the application needs the web stack.

### 10.3 Upgrading the Plugin While Forgetting the BOM Strategy

With the `dependency-management` plugin, the BOM follows the plugin version automatically. With a native BOM, the BOM version is written separately. Check the exact strategy before changing versions; do not guess based on file names.

### 10.4 Importing the BOM While Forgetting the Maven Plugin

When using a corporate parent and only importing the BOM, Maven receives dependency management but does not automatically inherit plugin management/repackage execution from `spring-boot-starter-parent`. If the goal is an executable JAR, configure `spring-boot-maven-plugin` and the `repackage` execution.

### 10.5 Using Version Overrides to Mask Conflicts

A direct version line may make the build resolve, yet produce a set of Spring modules skewed off the release train. Before overriding, use `dependencyInsight` or `dependency:tree` to identify which module pulls in a different version and why.

### 10.6 Using enforcedPlatform as the Default

`enforcedPlatform` forces platform versions onto the dependency graph. It can affect even transitive dependencies required by other libraries. Only use it when there is a clear policy and sufficient testing.

### 10.7 Upgrading Plugin, Gradle Wrapper, and JDK Simultaneously Without a Baseline

When multiple layers change at once, resulting errors are hard to attribute. Unless forced to change simultaneously, separate build tool/JDK changes from Boot plugin/BOM changes for clearer diffs and tests.

---

## 11. Upgrade Pull Request Review Checklist

### Versions and Management Sources

- [ ] Recorded current Boot version and target version.
- [ ] Identified Gradle `dependency-management` plugin vs. native BOM support.
- [ ] If using `dependency-management` plugin, understood that the BOM auto-imports per Boot plugin version.
- [ ] If using native BOM, updated and reviewed the `platform` version separately.
- [ ] If using Maven, distinguished starter parent from BOM import.
- [ ] Identified plugin version/execution when not using the Spring Boot parent.
- [ ] Reviewed direct dependency overrides, constraints, and version catalog.
- [ ] No multiple unexplained sources managing the same version.

### Compatibility and Verification

- [ ] JDK fits the Boot release.
- [ ] Gradle/Maven Wrapper is within the supported version range.
- [ ] Third-party plugins are compatible.
- [ ] Read release notes and migration guide.
- [ ] Saved before/after runtime dependency trees.
- [ ] Verified Spring Framework modules and key libraries.
- [ ] Dependency overrides have rationale and tests.
- [ ] `clean check` or `clean verify` passes.
- [ ] Executable JAR/WAR is created and `java -jar` runs.
- [ ] Container smoke test passes if deploying containers.
- [ ] Recorded tested artifact/image digest.

---

## 12. Practice Exercises

### A. Identify the Correct Version Layer

For each change, identify whether it belongs to the plugin, BOM, or application dependencies:

1. Changing `org.springframework.boot` Gradle plugin from 3.2.x to 3.3.13.
2. Changing `spring-boot-dependencies` platform from 3.2.x to 3.3.13.
3. Adding `spring-boot-starter-validation`.
4. Upgrading `com.acme:partner-sdk` from 4.2.0 to 4.3.0.
5. Changing Gradle Wrapper from 7.x to 8.x.
6. Changing Java toolchain from 17 to 21.

Explain which changes can alter the runtime dependency graph and which primarily affect the build environment.

### B. Switching from dependency-management Plugin to Native BOM

1. Save the runtime dependency tree before converting.
2. Record the Boot plugin version and actual BOM.
3. Remove `apply plugin: 'io.spring.dependency-management'` in a lab branch.
4. Import the same BOM using `platform(...)`.
5. Re-resolve the dependency graph.
6. Compare differing versions and explain the causes.
7. Run tests and executable packaging.
8. Only conclude the two approaches are equivalent after verifying the dependency graph and required behavior.

### C. Maven Parent vs. BOM Import

1. Create a Maven project using `spring-boot-starter-parent`.
2. View `help:effective-pom`.
3. Switch to a simulated corporate parent and import `spring-boot-dependencies`.
4. Add `spring-boot-maven-plugin` with version and `repackage` execution.
5. Compare the effective POM and produced artifact.
6. Explain which plugin management entries are no longer inherited from the Spring Boot parent.

### D. Finding Dependency Overrides

1. Run `dependencyInsight` or `dependency:tree`.
2. Pick a module managed by the BOM.
3. Add a direct version override on a lab branch.
4. Observe the actual resolved version change.
5. Remove the override and verify the BOM manages it again.
6. Document why overrides can skew dependencies away from the release train.

### E. Designing an Upgrade Workflow

Write a PR plan covering target Boot release, JDK/Gradle/Maven compatibility, plugin/BOM strategy, application dependency changes, dependency graph diff, test matrix, artifact/container verification, and rollback plan.

Do not mark "upgrade successful" just because the build script no longer reports configuration errors.

---

## 13. Official References

- Spring Boot 3.3.13 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot 3.3.13 — Managing Dependencies with dependency-management plugin or native BOM support: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3.13 — Gradle Plugin Reference: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3.13 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3.13 — Maven Plugin, parent POM and importing BOM without parent: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot — Build Systems and Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Gradle — Platforms and BOM support: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
- Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle — Plugin Management: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- Apache Maven — Dependency Management: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

**Key takeaway:** The Spring Boot Gradle plugin manages build behavior and packaging; the BOM manages dependency versions; application dependencies determine which libraries are included in the application. With the Gradle `dependency-management` plugin, the BOM automatically follows the Boot plugin version by default. With native BOM or separate Maven BOM import, the BOM version is declared separately. Before upgrading, identify version sources, inspect the actual dependency graph, and verify the executable artifact.
