# Distinguishing Dependency Declaration from dependencyManagement

When working with Spring Boot, Maven, and Gradle, two actions are easily confused: **declaring a library you need** and **managing versions/selection rules for libraries**. They are closely related, yet answer two different questions:

- **Dependency declaration:** "Which components does this project need to compile, run, or test?"
- **Dependency management:** "When a component appears in the dependency tree, what version and related rules should be selected?"

Core rule: **version management does not make a library appear on the classpath by itself**. A library enters the dependency tree only when declared directly or pulled in via a *transitive dependency* relationship. The Spring Boot BOM is a prime example of a version management mechanism.

## 1. Two Distinct Responsibilities in One Dependency Graph

Suppose a REST application needs `spring-boot-starter-web`. When you declare this starter, the build tool places the starter into the dependency graph and traverses the components it needs, such as Spring Web, Spring MVC, and other libraries matching the version in use.

Spring Boot's BOM (*Bill of Materials*), on the other hand, contains **version management information** for many modules. The BOM helps modules in the ecosystem get selected from a set of versions tested together. Importing the BOM alone without declaring a starter or other libraries will **not give your application Spring MVC, Jackson, or a web server**.

~~~text
DEPENDENCY DECLARATION (picks "what is needed")
  spring-boot-starter-web
          |
          +--> spring-webmvc
          +--> spring-web
          +--> other transitive dependencies

VERSION MANAGEMENT (picks "which version")
  spring-boot-dependencies BOM
          |
          +--> version rules for Spring modules
          +--> version rules for many third-party libraries

Resolved result = Actually present dependencies
                + Transitive relationships
                + Management rules / conflict resolution.
~~~

Not every entry listed in a BOM appears on the classpath; only entries actually needed in the graph have their version selected. Conversely, declaring a dependency without suitable version management rules may force you to specify a version directly or let the system resolve via another mechanism.

## 2. Maven: How `<dependencies>` Differs from `<dependencyManagement>`

In Maven, this distinction is expressed directly through two XML sections.

### 2.1. `<dependencies>`: Requesting an Actual Dependency

Example snippet in `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
</dependencies>
~~~

Maven gets a direct dependency on `spring-boot-starter-web`. It will resolve additional transitive dependencies per the artifact's metadata and active management rules. This example only illustrates **actual declaration**; in a Spring Boot project managed by a BOM or starter parent, you usually **do not repeat the starter's version**.

Key attributes in a dependency declaration:

| Attribute | Meaning |
| --- | --- |
| `groupId` + `artifactId` | Identifies the library |
| `version` | Requested version; can be omitted when properly managed |
| `scope` | Scope such as `compile`, `runtime`, `test`, `provided` |
| `optional` | Restricts the dependency from propagating to consuming projects as a transitive dependency |
| `exclusions` | Excludes specific transitive dependencies from the declared branch |

`<dependencies>` answers "what the project is using," though whether an artifact is downloaded also depends on scope, profiles, version selection, and transitive branches.

### 2.2. `<dependencyManagement>`: Declaring Default Rules

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>3.3.5</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This block manages the version for `spring-boot-starter-web`, yet **does not create a direct dependency** in the project from this XML alone. To use the starter, you must declare it:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Maven can then obtain version `3.3.5` from `dependencyManagement`. This is a **rules + actual need** relationship.

`dependencyManagement` can also influence version selection for **transitive** dependencies when artifact coordinates match. So do not think of it as "only applies to directly declared dependencies." What is accurate is that management **does not add a dependency branch by itself**, yet can govern a dependency's version if another branch pulls it into the graph.

### 2.3. Quick Comparison in Maven

| Configuration Present | Requests downloading `spring-boot-starter-web` as an app dependency? | Where does the version come from? |
| --- | --- | --- |
| Only `<dependencyManagement>` managing the starter | **No** | Version rule exists, but no usage demand yet |
| Only `<dependencies>` with starter and `<version>` | **Yes** | Version written directly |
| `<dependencies>` has starter without version; management manages starter | **Yes** | Version provided by management |
| Only Spring Boot BOM imported | **No** | BOM supplies many rules, does not add starter itself |
| Import BOM **and** declare starter | **Yes** | BOM manages starter version and many related dependencies |

In a `pom.xml` with no version on a dependency and no matching version from management/parent, Maven normally reports a missing-version error while building the project model. You cannot assume "omitting version" is always valid.

## 3. Spring Boot BOM: Importing a Managed Version Set

Spring Boot's BOM has coordinates `org.springframework.boot:spring-boot-dependencies`. It collects library versions tested by Spring Boot for a specific release.

### Approach A — Using `spring-boot-starter-parent` in Maven

The Spring Boot starter parent inherits Spring Boot's dependency management along with default plugin/build configurations. Minimal illustrative `pom.xml`:

~~~xml
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
    <artifactId>dependency-demo</artifactId>
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
</project>
~~~

Here there are two actual needs: the web starter and the test starter. Neither specifies a version because the parent supplies dependency management. `spring-boot-starter-test` has `scope=test`, so test-only libraries do not become main runtime dependencies of the application.

`3.3.5` is simply a **fixed version for the example**, not an implication that it is the latest Spring Boot release or recommended for new projects. To produce an executable Spring Boot JAR from Maven, add/configure `spring-boot-maven-plugin` per the packaging workflow; dependency management by itself does not create an executable JAR.

### Approach B — Importing the BOM When Not Using Starter Parent

A project may need to inherit from another Maven parent. In that case, import the Spring Boot BOM directly inside `<dependencyManagement>`:

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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

This is a **configuration snippet placed inside `<project>` of `pom.xml`**, not a standalone POM. A BOM import requires both `<type>pom</type>` and `<scope>import</scope>` inside the management block. Once imported, dependencies below can omit versions managed by the BOM.

Distinguish this from a dependency with `runtime` scope: `import` inside `dependencyManagement` does **not** add the BOM as a JAR on the runtime classpath; it merges the BOM's management rules into the build model.

**Note on parent:** importing the BOM brings dependency management; it **does not bring along all `pluginManagement`/build defaults** supplied by `spring-boot-starter-parent`. When not using the starter parent, you must configure `maven-compiler-plugin`, `spring-boot-maven-plugin`, and required plugins yourself. `dependencyManagement` does not substitute for `pluginManagement`.

## 4. Gradle: Different Terms, Same Separation of Need and Management

Gradle does not use Maven's `<dependencies>` and `<dependencyManagement>` XML tags as a native configuration language. It typically declares dependencies by **configuration** and manages versions via **platforms/BOMs, dependency constraints**, or Spring's dependency management plugin.

### 4.1. `dependencies`: Adding Libraries to Configurations

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.5'
}
~~~

This is an illustrative `build.gradle` snippet, assuming the Java plugin is applied and repositories are configured. `implementation` adds the dependency for compiling/running main code; `testImplementation` serves test code.

In real projects using a Spring Boot BOM, omitting versions on BOM-managed dependencies reduces repetition and prevents ecosystem libraries from drifting out of sync.

### 4.2. Native Gradle BOM via `platform(...)`

Gradle supports importing a BOM as a platform dependency without needing an external dependency management plugin:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a valid `build.gradle` for inspecting/resolving the dependency graph with a compatible Gradle version. `platform(...)` introduces **version constraints** from the BOM into resolution. Only the line `implementation '...starter-web'` requests the starter. Removing that line leaves you with an imported BOM that adds no web libraries on its own.

Gradle resolves version conflicts using its own resolution engine. A regular platform supplies version constraints/recommendations from metadata; **do not assume a regular BOM enforces every version absolutely** when competing requirements exist. `enforcedPlatform(...)` applies stronger enforcement and can affect downstream projects consuming a library you publish; use it only when you understand the consequences.

### 4.3. Spring Boot Gradle Plugin + `io.spring.dependency-management`

Another common option:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When **both** the Spring Boot Gradle plugin and `io.spring.dependency-management` are applied, the Spring Boot integration can automatically import the `spring-boot-dependencies` BOM matching the Boot plugin version, allowing the starters above to omit versions. This behavior is specific to that plugin pairing; do not infer that applying **only** `org.springframework.boot` automatically manages versions the way `io.spring.dependency-management` does.

When using `io.spring.dependency-management` on its own, BOM import syntax can be written explicitly:

~~~groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.5'
    }
}
~~~

This snippet is valid only when the corresponding plugin is applied. It imports management rules and does **not** add `spring-boot-starter-web`. Pick one consistent strategy for the project instead of importing the BOM multiple times with different versions.

### 4.4. Dependency Constraints and Version Catalogs Are Not Actual Dependencies

Gradle also offers `constraints` to define version selection rules for modules:

~~~groovy
dependencies {
    constraints {
        implementation('org.apache.commons:commons-lang3:3.14.0')
    }
}
~~~

This constraint alone will not cause `commons-lang3` to appear as a runtime JAR if the dependency graph never needs it. Once a dependency actually needs that artifact, the constraint can influence version resolution; the exact outcome still depends on competing constraints.

Likewise, `gradle/libs.versions.toml` (*version catalog*) is a convenient list of names/versions/aliases for **referencing** dependencies and plugins. Having an alias in the catalog does not add any dependency to the project; you must still reference the alias inside `dependencies` or plugin configuration. A version catalog does not replace a BOM's role in aligning transitive versions.

### Conceptual Mapping Between Maven and Gradle

| Intent | Maven | Gradle |
| --- | --- | --- |
| Request a library for main code | `<dependencies><dependency>...` | `implementation 'group:artifact'` |
| Request a library for tests | `<scope>test</scope>` | `testImplementation 'group:artifact'` |
| Centralized version management | `<dependencyManagement>` | `platform(...)`, constraints, or dependency-management plugin |
| Import Spring Boot BOM | `<type>pom</type>` + `<scope>import</scope>` in management | `platform('...spring-boot-dependencies:...')` or `mavenBom` |
| Inherit build and dependency defaults from Boot | `spring-boot-starter-parent` | Combination of Gradle plugins/build config; no direct Maven parent equivalent |
| Inspect selected versions | `mvn dependency:tree` | `./gradlew dependencies` / `dependencyInsight` |

Scopes/configurations in the two build tools do not map strictly one-to-one. Consider the module type (application vs. library) and specific purpose. For example, Gradle `api` is available only with the `java-library` plugin; do not confuse `api` with `implementation` when publishing libraries.

## 5. Direct, Transitive, and Effective Versions

Suppose there are three nodes:

~~~text
Application
  |
  +-- direct: spring-boot-starter-web
                    |
                    +-- transitive: spring-webmvc
                    +-- transitive: other libraries
~~~

- **Direct dependencies** are declared in Maven's `<dependencies>` or Gradle's `implementation`/corresponding configuration.
- **Transitive dependencies** enter because a direct (or another transitive) dependency requires them.
- **Managed versions/constraints** can affect both direct and transitive components if the module falls under the rule.

For example, the Spring Boot BOM manages several Jackson libraries. When the web starter brings Jackson into the graph, Jackson's version management rules can apply. That does **not** mean importing the BOM alone causes Jackson to appear; it appears because of an actual dependency edge.

### What Happens When Declaring a Version Directly?

In **Maven**, an explicit version written on a direct dependency declaration is normally the specific request for that dependency; `dependencyManagement` rules typically supply versions **when declarations omit versions** or coordinate versions across the transitive graph. Conflicting versions remain subject to Maven mediation and management rules.

In **Gradle**, version requests, platform constraints, explicit constraints, and conflict resolution rules all participate in picking the final version. Writing a version in dependency notation does not always hard-lock that version; to know what was truly chosen, **inspect the resolved graph**.

It is critical to distinguish:

1. **Requested version:** the version asked for by a declaration or transitive dependency.
2. **Managed/constrained version:** the version recommended, managed, or constrained by parent/BOM/constraints.
3. **Resolved version:** the final version chosen by the build tool for the given configuration/scope.

Do not rely solely on `pom.xml` or `build.gradle` to deduce every JAR present at runtime.

## 6. Before–After Example: From Repeated Versions to Centralized Management

**Before — Maven specifying versions individually per dependency:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <version>3.3.5</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**After — importing a BOM in management while keeping the library declarations:**

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
~~~

These two snippets are **configuration fragments inside `<project>`**, not two standalone runnable apps. After migrating, the starter list **remains explicitly declared**: management only changes where versions are decided. The benefit is upgrading the BOM version centrally and reducing the chance of declaring incompatible Boot ecosystem dependencies.

**Note:** The BOM can manage versions of many transitive modules beyond those two starters; thus even though direct starters stay the same, the dependency tree after migration can differ if you previously pinned versions manually elsewhere. Inspect the dependency tree and run tests whenever changing the management mechanism.

## 7. Verify with Commands Instead of Guessing

### Maven

From the directory containing `pom.xml`:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

- `help:effective-pom` shows the POM after parent inheritance, BOM imports, and effective configuration. You can check the management section inside it to verify managed versions.
- `dependency:tree` shows the dependencies actually resolved by scope and tree edges. A module present only in `dependencyManagement` with no actual dependency path will not appear as an application JAR dependency.
- `-Dincludes=...` filters for the artifact coordinates of interest. Commands may need to download Maven plugins/dependencies on first use.

To inspect runtime and tests, check each dependency's exact scope rather than scanning one artifact list and assuming everything is packaged. When spotting an unexpected version, inspect parent, management, direct declarations, and transitive paths.

### Gradle

On Linux/macOS using the Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
~~~

On Windows, replace `./gradlew` with `gradlew.bat`. `dependencies` prints the graph per configuration; `dependencyInsight` explains why a version was chosen, showing requests and paths. Output depends on plugins, repositories, Gradle version, and actual graph, so **do not assume a fixed stdout** for these commands.

When only importing `platform`/BOM without declaring a starter, test it yourself: you may see platform/constraint entries yet **no** web dependency as a runtime library merely because the BOM lists it.

To run a controlled experiment: start from a minimal project, import the BOM, inspect the graph; then add one `implementation 'org.springframework.boot:spring-boot-starter-web'` line or Maven `<dependency>` equivalent, re-run the graph, and compare. That clearly demonstrates how **adding dependency demand** differs from **version management**.

## 8. Common Confusions with dependencyManagement

### 8.1. "I declared the BOM—why can't my code import Spring Web?"

Because a BOM only manages versions. Add the needed dependency to `<dependencies>` or `implementation`. Then check scope/configuration, repositories, and compilation tooling. If source code imports Spring Web while the dependency is only in `testImplementation`, main code cannot see that library.

### 8.2. "I declared the starter—why does Maven report a missing version?"

Check whether the POM actually inherits an appropriate parent or imports the BOM with proper `type=pom`, `scope=import` syntax inside `dependencyManagement`. Inspect the effective POM and `groupId:artifactId` coordinates. Also, the BOM may not manage an arbitrary library outside its supported set; such libraries need their own version/management.

### 8.3. "Why is a library present at runtime when I never declared it directly?"

It may have been pulled in **transitively**. Run `dependency:tree` or `dependencyInsight` to identify which path requested it. Version management does not explain *why* a library was requested; it mainly participates in deciding *which version* is chosen.

### 8.4. "I have a BOM—why do two modules still use a different version than I expected?"

Possible causes include an explicit version on a direct dependency, another BOM, another parent, conflict resolution rules, constraints, dependency locks, or plugins configured elsewhere. A BOM version is not always the final version in Gradle. Inspect the **resolved graph**, not just artifact names in build files.

### 8.5. "Does `dependencyManagement` replace `spring-boot-maven-plugin`?"

No. Dependency management manages project dependencies. `spring-boot-maven-plugin` is a build plugin supplying goals like `repackage`; similarly, `spring-boot-gradle-plugin` adds tasks like `bootJar`. Using a BOM does not configure all packaging steps, and the packaging plugin does not replace declaring the starters your application needs.

### 8.6. "Can I put all dependencies in the parent POM for child modules to use?"

Parent `<dependencies>` in Maven are inherited as **actual dependencies** by child modules. If you only want to centralize **version rules** without forcing every child module to carry the same dependencies, place versions in the parent's `<dependencyManagement>` and let each child module declare the dependencies it actually needs. This is a key benefit of management in multi-module projects.

### 8.7. "What if I want to override a BOM-managed version?"

There may be valid reasons like patching a security vulnerability, yet it must be backed by compatibility checks, testing, and the resolved graph. How you override depends on whether you use Maven starter parent, Maven BOM import, Gradle `platform`, or the dependency-management plugin. **Do not assume changing a POM property always overrides an imported BOM**: property/precedence mechanics differ between parent inheritance and imported BOMs. Use the override mechanism supported by your actual setup and verify the final version.

### 8.8. "A Gradle version catalog already defines the starter—why is the dependency missing?"

An alias in `libs.versions.toml` is just declaration metadata for convenient referencing. It does not add any module automatically. The project must still use the alias in the appropriate `dependencies` block; and referencing an alias does not automatically apply a BOM to manage all transitive dependencies.

## 9. Process for Choosing the Right Mechanism in a Spring Boot Project

1. **Identify the libraries actually needed.** Pick starters and dependencies by capability, distinguishing main/test/compile-only/runtime-only.
2. **Choose one consistent version management strategy.** Maven can use the Spring Boot starter parent or import the Boot BOM. Gradle can use native `platform` or the dependency-management plugin integration, depending on project structure.
3. **Ensure management aligns to one compatible Spring Boot release.** Avoid accidentally mixing versions across the Boot plugin, BOM, starters, and framework modules.
4. **Avoid repeating versions when management rules already cover them**, unless you have a clear reason and understand precedence.
5. **Inspect the effective configuration and resolved graph** after changes. Prefer inspecting `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath` separately (Gradle) or the corresponding scopes (Maven).
6. **Run the build and tests**, especially when changing BOM/parent/Gradle constraints, because a managed version change can affect many transitive dependencies without any source code changes.

A short decision table:

| What do you want to do? | Where to edit |
| --- | --- |
| Use Spring MVC for the application | Declare `spring-boot-starter-web` in dependencies |
| Ensure Boot libraries pick synchronized versions | Boot BOM / starter parent / Gradle platform or dependency management |
| Library needed only for testing | Scope `test` (Maven), `testImplementation` (Gradle) |
| Update versions for the entire Spring Boot-managed dependency set | Update the Boot parent/BOM release or the version used for import |
| Verify the actually selected version | Maven `dependency:tree`/`effective-pom` or Gradle `dependencies`/`dependencyInsight` |
| Build an executable Boot archive | Configure and run the corresponding Spring Boot Maven/Gradle build plugin |

## 10. Self-Check Questions

**Question 1.** A Maven project only imports `spring-boot-dependencies` with `scope=import`. Does the project already have `spring-boot-starter-web` in its dependency tree?

**Answer:** You cannot assume yes; a BOM by itself does not declare a requirement to use the starter. A direct dependency or an actual transitive path is needed.

**Question 2.** Maven has management for `spring-boot-starter-web` version `3.3.5` and a starter dependency declaration without a version. Where does the version come from?

**Answer:** From effective `dependencyManagement` (assuming no other configuration overrides selection). This is an actual dependency supported by version management.

**Question 3.** Gradle has `implementation platform('...spring-boot-dependencies:3.3.5')` without `implementation '...spring-boot-starter-web'`. Can main code automatically use Spring MVC?

**Answer:** Not from the platform alone; the appropriate dependency must be on the compile classpath.

**Question 4.** A library not declared directly is still present in `runtimeClasspath`. Did the BOM "pull" it in?

**Answer:** Normally you must trace which transitive dependency path requested it. A BOM/platform can influence the selected version, yet does not create ordinary library dependency edges by itself.

**Question 5.** A library in the BOM is managed at version A, yet the dependency graph shows version B. What should you inspect?

**Answer:** Direct version declarations, other parents/BOMs, constraints, conflict resolution, dependency locks, and the resolved graph. Managed version and actual version must be clearly distinguished.

**Takeaway:** **Dependency declarations create demand; `dependencyManagement`/BOMs govern version selection; the resolved dependency graph is the actual outcome.** Separating these three layers helps you fix the right issue when encountering missing libraries, version conflicts, or Spring Boot upgrades.