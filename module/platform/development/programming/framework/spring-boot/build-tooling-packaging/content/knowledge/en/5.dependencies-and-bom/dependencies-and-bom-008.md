# Comparing io.spring.dependency-management with Gradle platform and enforcedPlatform in Spring Boot

## 1. Context: Why Does Spring Boot Use a BOM?

A Spring Boot application typically uses many interdependent libraries: Spring Framework, Jackson, Logback, Micrometer, Spring Boot starters, database drivers, testing libraries… Manually assigning a version to each library easily creates combinations never tested together. Spring Boot publishes a **BOM (Bill of Materials)** named `org.springframework.boot:spring-boot-dependencies`, listing managed versions of many modules.

A BOM **manages versions**; it does not add libraries to the application by itself. You still must declare the modules actually needed, such as `org.springframework.boot:spring-boot-starter-web`. When the BOM manages that module, you can omit the version in the dependency declaration.

In a Gradle build, there are three common ways to apply version rules from a BOM:

1. The Spring community plugin `io.spring.dependency-management`: provides a Maven-like dependency management model and supports customizing versions through BOM properties.
2. `platform(...)`: a native Gradle feature; imports BOM versions into Gradle's **dependency constraints** system to participate in version selection.
3. `enforcedPlatform(...)`: also a native Gradle feature, yet demands BOM versions in a **forced/strict** manner in the dependency graph.

**Lesson scope:** comparing version selection and Gradle configuration for Spring Boot projects. `org.springframework.boot` is the **Spring Boot Gradle plugin** for building/packaging Boot; `io.spring.dependency-management` is a separate plugin for dependency management. The two plugins have distinct responsibilities.

## 2. Quick Comparison Table

| Criterion | `io.spring.dependency-management` | `platform(...)` | `enforcedPlatform(...)` |
|---|---|---|---|
| Mechanism | Spring plugin managing dependencies via BOM/Maven-style DSL | Native Gradle platform, importing BOM as dependency constraints | Native Gradle platform, forcing BOM versions via strict constraints |
| When Spring Boot Gradle plugin is applied | Boot **automatically imports** the matching BOM when the dependency management plugin is applied | Must declare the platform dependency explicitly | Must declare the enforced platform dependency explicitly |
| Can version be omitted on BOM-managed dependencies? | Yes | Yes, within affected configurations | Yes, within affected configurations |
| When another library requests a higher version than the BOM | Follows the plugin's management rules and overrides/forces; verify the outcome | Gradle can select a version higher than the BOM after conflict resolution | Attempts to retain the BOM version; can fail on conflicting strict requirements |
| Customize Spring Boot BOM properties | Yes, e.g., `slf4j.version` | Not via BOM properties | Not via BOM properties |
| Customize via Gradle constraints/rules | Can coexist, but interactions must be verified | Gradle's natural mechanism | Can add rules, but watch for strict conflicts |
| Configuration scope | Plugin manages broadly by default; provides DSL to scope configurations | Declared configuration and configurations extending it | Similar to `platform` |
| Propagation to consumers | Integrates with Maven POM publishing via plugin; check published output | Platforms/constraints can propagate by variants, metadata, and publication type | Extra caution needed: forced versions can propagate to consumers |
| Build performance/setup | Adds an extra plugin and dependency processing layer | Built into Gradle; Spring Boot notes it is often faster | Built into Gradle; stronger enforcement than `platform` |
| Typically chosen when? | Projects needing Maven-like management or BOM property overrides | Most projects wanting native mechanics and allowing Gradle to mediate versions | Apps needing strict BOM-pinned versions across the graph, after weighing impact |

**`platform` does not "ignore the BOM."** The BOM still contributes constraints and usually determines the version when there are no competing requests. Differences show up primarily when the dependency graph has competing version requests.

## 3. Underlying Mechanism: From Dependency Declaration to Actual Version

Suppose a BOM manages a hypothetical module `org.example:lib` at `1.5`; another dependency requests `org.example:lib:1.7`. These are **illustrative version numbers**, not real Spring library versions.

- With `platform`, Gradle treats version `1.5` from the BOM as a normal constraint. A `1.7` request elsewhere in the graph can cause `1.7` to be selected.
- With `enforcedPlatform`, version `1.5` becomes a forced requirement; Gradle favors `1.5` over ordinary version requests. If incompatible `strictly` constraints exist, resolution can fail rather than quietly "picking one."
- With `io.spring.dependency-management`, the plugin applies managed versions through its own engine (accounting for declarations and rules). Never assume a single fixed numerical outcome across every graph; run `dependencyInsight` to confirm.

A BOM is a set of **version rules for modules present in the graph**. It does not guarantee every library comes from the BOM: libraries unmanaged by the BOM still require versions/constraints from elsewhere.

A Spring Boot release is tested with a specific set of dependency versions. **Forcing every version to the BOM** keeps you aligned with that set, yet does not automatically guarantee compatibility with every out-of-BOM library. **Allowing version bumps** may be necessary for security fixes, yet requires testing and checking API/ABI compatibility.

## 4. Approach 1 — Using io.spring.dependency-management

### 4.1. What Does This Plugin Do?

`io.spring.dependency-management` imports one or more Maven BOMs and applies dependency management across a Gradle project's dependencies, including both direct and transitive dependencies under the plugin's model. It provides the `dependencyManagement { ... }` DSL, supports BOM imports, module version overrides, reading BOM version properties, and some Maven exclusion semantics.

In a **project that already applies `org.springframework.boot`**, simply also applying `io.spring.dependency-management` causes the Spring Boot Gradle plugin to **automatically import** the `spring-boot-dependencies` BOM matching the Boot plugin version. You do not need to write `dependencyManagement { imports { mavenBom ... } }` just to re-import that same BOM.

Complete Groovy `build.gradle` example for build setup (running an app still needs a main Java class):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Both dependencies omit versions because the BOM is imported automatically when **both plugins** are present. `3.5.16` and `1.1.7` are illustrative published versions; in real projects pick compatible Boot, Gradle Wrapper, and JDK versions and keep a single consistent version source.

Kotlin DSL equivalent `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

These examples are written for Spring Boot Java/Gradle projects. They are not standalone Java files runnable with `javac`; running Boot also depends on Java sources and the project's entry point.

### 4.2. The Plugin Alone Does Not Automatically Import the Spring Boot BOM

If a library module applies only `java-library` and `io.spring.dependency-management` **without applying the Spring Boot Gradle plugin**, importing the Spring Boot BOM manually may be necessary:

```groovy
// Snippet added to build.gradle of a module that applies
// io.spring.dependency-management without the Boot plugin.
dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}
```

That means **"the plugin is applied" does not imply "every BOM is auto-imported."** Importing the BOM manually in a module without the Boot plugin is valid when you want a library to share the Spring Boot dependency set without turning it into a Boot executable application.

### 4.3. Advantage: Overriding via BOM Properties

A Maven BOM can declare many versions via properties. The Spring Boot BOM publishes properties like `slf4j.version`; with the dependency management plugin, you can adjust managed versions through those property values:

```groovy
// Illustrative snippet in build.gradle (Groovy DSL)
ext['slf4j.version'] = '2.0.17'
```

Kotlin DSL equivalent:

```kotlin
extra["slf4j.version"] = "2.0.17"
```

**This is only illustrative syntax**, not a recommendation to apply that version to a specific Boot release. Before changing, look up the exact property name in "Dependency Versions Properties" for your Spring Boot version, identify affected modules, and test compatibility. Changing a property for a module group can affect more dependencies than anticipated.

The plugin also allows overrides via explicit dependency management, e.g., inside a plugin-managed module:

```groovy
dependencyManagement {
    dependencies {
        dependency 'com.zaxxer:HikariCP:5.0.0'
    }
}
```

Pick a real version compatible with your library stack. When publishing a Maven POM for a library, **property overrides may not be accurately reflected in the generated POM**, whereas explicit dependency management overrides can appear in `<dependencyManagement>`. Inspect the actual published artifact before promising consumers the same rules.

### 4.4. Multiple BOMs and Exclusions

The plugin supports importing multiple BOMs. When two BOMs manage the same module, **import order matters**: in the dependency management plugin, the BOM imported later normally wins for overlapping modules per plugin docs. Example scenario: a shared BOM and a domain-specific BOM both declare Jackson versions; simply swapping import order can alter the managed version.

The plugin also supplies Maven-like exclusions in its DSL and honors exclusions in Maven POMs according to its model. That is a feature difference compared to using native platform constraints alone. However, that does not mean every Java/Gradle exclusion behaves identically to Maven in all cases (for example, classifier limitations documented by the plugin).

### 4.5. Limitations and Things to Remember

- Adding a plugin adds another layer of dependency processing; Spring Boot recommends considering native BOM support since it is often faster.
- Managed versions follow the plugin's mechanism, not Gradle's native `platform`; when mixing with `strictly`, platforms, or resolution rules, inspect the actual resolver output.
- In a Boot app using this plugin, avoid redundantly re-importing the Boot BOM without a concrete reason.
- When publishing a library, check both the Maven POM and Gradle Module Metadata if consumers use different build tools.

## 5. Approach 2 — Using Gradle's Native platform(...)

### 5.1. Importing a BOM as Dependency Constraints

Gradle has built-in `platform(...)` support for consuming a Maven BOM. It treats the POM's `<dependencyManagement>` section as dependency constraints in the graph. You do not need to apply `io.spring.dependency-management`.

Spring Boot project example in Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Here `SpringBootPlugin.BOM_COORDINATES` is a constant provided by the Spring Boot Gradle plugin. It resolves to the exact BOM coordinates and version matching the applied plugin version, so you avoid repeating `org.springframework.boot:spring-boot-dependencies:3.5.16`.

Kotlin DSL equivalent with both `platform` declarations:

```kotlin
dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

The Kotlin snippet goes inside a `build.gradle.kts` that already has `plugins { java; id("org.springframework.boot") version "3.5.16" }` and `repositories { mavenCentral() }` like the Groovy example. It uses valid Kotlin DSL syntax, yet does not form a complete project by itself.

**Why declare on both `implementation` and `testImplementation`?** A platform affects only the configuration containing it or configurations extending it. Under the Java plugin, certain test configurations inherit from main `implementation`; declaring it explicitly in the example shows clear intent to manage test versions as well. Check your real project's configuration hierarchy to avoid unnecessary duplication.

For a Java library module **not applying the Boot plugin**, use explicit BOM coordinates:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
}
```

When upgrading Spring Boot in such a module, update the BOM through your build's centralized version management; there is no plugin constant to sync it automatically.

### 5.2. What Does "Recommended" Mean?

A BOM version imported with `platform` normally becomes a **non-forcing** constraint. If a transitive dependency requests a newer version, Gradle may select that newer version via conflict resolution. Therefore:

- `platform` **supplies consistent versions when there are no competing requests**.
- `platform` allows **Gradle to mediate conflicts** with other versions/constraints; the outcome can diverge from the BOM.
- `platform` **does not block** all transitive upgrades; if security or compatibility requires an exact version, consider rich versions, strict dependency constraints, or another strategy.

A dependency change, even without touching the `platform` line, can alter selected versions. After upgrading an out-of-BOM library, always inspect `runtimeClasspath` and run tests.

### 5.3. Customizing Versions via Gradle Mechanisms

Native `platform` **does not read override properties in the Spring Boot BOM the way the plugin does**. For example:

```groovy
ext['slf4j.version'] = '2.0.17'
```

When using `platform` alone, that line **will not change** the SLF4J version from the imported BOM. To override it, use Gradle's native mechanisms, such as a dedicated dependency constraint:

```groovy
dependencies {
    constraints {
        implementation('org.slf4j:slf4j-api') {
            version {
                strictly '2.0.17'
            }
            because 'Example of an explicit version constraint'
        }
    }
}
```

This snippet sets a strict constraint on the **single module** `slf4j-api`; it does not adjust all SLF4J modules or other BOM properties automatically. If another incompatible strict constraint exists, resolution can fail. It illustrates the technical mechanism, not advice to arbitrarily downgrade a Spring Boot library.

Other options include constraints with `require`/`prefer`, `resolutionStrategy.eachDependency`, or version catalogs paired with constraints. A **version catalog** only centralizes declared names and versions; it does not import a BOM or guarantee all transitive dependencies receive that version.

## 6. Approach 3 — Using enforcedPlatform(...) to Force BOM Versions

When you want the BOM to **strongly dictate** versions for the modules it manages, Gradle provides `enforcedPlatform(...)`.

Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation enforcedPlatform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation enforcedPlatform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Kotlin DSL, inside a project applying the Spring Boot plugin:

```kotlin
dependencies {
    implementation(
        enforcedPlatform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        enforcedPlatform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Per Gradle, `enforcedPlatform` converts the BOM's version constraints into **strict/forced** versions in the graph. When another dependency requests an ordinary higher version, the enforced BOM typically retains its version. That behavior must be deliberate, because a library compiled/tested against a higher version may be incompatible with a forced lower version.

**Warning when publishing libraries:** Enforced platforms have a **transitive** effect and can appear in library consumers' dependency graphs when publications carry the relevant metadata. Gradle advises caution because consumers may be forced onto versions from your BOM; if conflicts arise, they may have to exclude dependencies or tweak the graph. This matters far more for shared SDKs/libraries than for a final Boot application not consumed as a dependency.

**Do not use `enforcedPlatform` blindly to resolve one vague conflict:** it can force **every module in the BOM**, including modules unrelated to the issue. First run `dependencyInsight` to examine paths and selection reasons, then decide on an appropriately scoped fix.

## 7. Version Selection Example When Conflicts Arise

Suppose we use a hypothetical library:

```text
BOM manages     org.example:codec:2.3
Module A        -> org.example:codec:2.5
Application     -> module A
```

| Option | Typical Outcome Trend | What to Verify |
|---|---|---|
| `platform(BOM)` | `codec:2.5` may be selected since the BOM constraint does not lock the version | Confirm version with `dependencyInsight` and run tests |
| `enforcedPlatform(BOM)` | `codec:2.3` is forced in ordinary graphs; strict conflicts possible | Does Module A still work with `codec:2.3`? |
| `io.spring.dependency-management` | Plugin applies managed/overridden versions per config; do not infer from native examples | Which overrides and rules does the plugin have? Which version did the resolver choose? |

**Examples are not a resolver guarantee for every situation.** Gradle also has version ranges, `strictly`, `reject`, dependency substitution, rules, multiple BOMs, and variant metadata. Another BOM might also constrain `codec`. Results must be verified on your project's own `runtimeClasspath` or `testRuntimeClasspath`.

A quick decision diagram:

```text
A module appears in the graph
             |
             v
       Is module in BOM?
          /        \
        No          Yes
         |           |
  Needs version   BOM contributes rules
  from elsewhere       |
                       v
            Plugin management or native?
                   /          \
               Plugin         Native
                 |              |
       Applies plugin      platform / enforcedPlatform
           rules              /           \
                         constraint     forced/strict
                             |               |
                         Can mediate     Prefers BOM-enforced
                         other version   version
```

## 8. Configuration Scope and Multi-Module Builds

In Gradle, dependencies always attach to a configuration such as `implementation`, `runtimeOnly`, `testImplementation`, `annotationProcessor`, or a custom configuration. `platform` and `enforcedPlatform` **do not automatically apply to every configuration**:

- `implementation(platform(...))` contributes constraints to resolvable configurations extending `implementation`, such as main classpaths under the Java plugin.
- If `annotationProcessor` or a custom configuration does not extend `implementation`, it needs its own constraint/BOM when managed versions are desired.
- `testImplementation` can inherit certain main dependencies, though you should not assume all custom test configurations behave identically.
- In a multi-project build, importing a BOM in project A **does not automatically** apply it to projects B/C. Each module or convention plugin must declare the appropriate management mechanism.

Example in Gradle Kotlin DSL for a module needing the BOM on its annotation processor (this is only a configuration snippet; it does not mean you always need an annotation processor):

```kotlin
dependencies {
    annotationProcessor(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
}
```

Use the `SpringBootPlugin.BOM_COORDINATES` constant only if the Boot plugin is on the build script classpath. Otherwise, use explicit BOM coordinates managed centrally.

In multi-module projects, consider a **convention plugin** or a **`java-platform` project** so the whole team uses one consistent mechanism. Avoid applying `io.spring.dependency-management` alongside `platform` for the same BOM in the same module "just to be safe"; mixing them obscures why versions are selected and makes debugging and upgrades harder.

## 9. Build-Time Versions vs. Versions Consumers Receive

"Which version is chosen on my machine?" differs from "Which constraints do consumers of my library receive?"

**With `io.spring.dependency-management`:** the plugin can modify the Maven POM generated by `maven-publish` to insert `<dependencyManagement>` entries when using global dependency management. A local BOM property override **is not necessarily** reflected as an overridden version in the published POM; the plugin recommends explicit dependency management overrides when the POM must show the change.

**With native `platform`:** constraints belong to Gradle's system. Whether constraints propagate to consumers depends on `api`/`implementation`, published variants, Gradle Module Metadata, and Maven POM mapping. Do not assume Maven consumers see every rule the same way Gradle consumers do.

**With `enforcedPlatform`:** Gradle warns it can impose versions on consumers transitively. For a reusable library, enforcing an entire BOM is usually too broad. If you only need to constrain one library, consider a **targeted** constraint or `strictly` rich version, tested against a consumer.

If your project is an **end Spring Boot service** packaged into a JAR and deployed (not published as a library dependency), downstream consumer propagation matters less. Even then, forcing versions still alters the dependency graph at build/test/runtime and can cause compatibility errors.

## 10. Inspecting Actual Versions Instead of Guessing

Using the project's Gradle Wrapper, run:

```bash
# View runtime dependency graph
./gradlew dependencies --configuration runtimeClasspath

# Analyze why a module was selected
./gradlew dependencyInsight \
  --dependency org.slf4j:slf4j-api \
  --configuration runtimeClasspath

# Inspect dependency graph for test runtime
./gradlew dependencies --configuration testRuntimeClasspath
```

On Windows PowerShell or Command Prompt, use `gradlew.bat`. `dependencyInsight` can be written on a single line to avoid shell line-continuation differences:

```text
gradlew.bat dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

Reading the results:

- `->` in the dependency tree indicates a version request was resolved/adjusted by Gradle to another version.
- `(c)` marks a dependency constraint; a constraint by itself does not mean the module was added to runtime.
- `dependencyInsight` shows selection reasons and dependency paths requesting versions, useful for distinguishing BOM recommendations from forced/strict constraints.
- With `io.spring.dependency-management`, the plugin offers a `dependencyManagement` task listing managed versions (if available in your plugin version). That task does not replace checking the **resolved version** with `dependencyInsight`.

Never quote a concrete version like "definitely picks 2.3" from a single build file without seeing the entire graph: version catalogs, constraints in other modules, rules, and transitive dependencies can all influence the result.

If a dependency is not yet in the graph, the BOM may still manage its version, yet `dependencyInsight` will not display that module on an unused configuration. Make sure you queried the right configuration and actually declared the dependency.

## 11. How to Choose for a Spring Boot Project

| Scenario | Consideration |
|---|---|
| New Boot service wanting Gradle's default dependency resolution | Start with `platform` |
| Existing project using `io.spring.dependency-management` with many BOM property overrides or needing Maven-style management | Keep the plugin if clearly justified; check compatibility when upgrading Gradle |
| End application needing strict adherence to BOM versions with verified dependencies | Can choose `enforcedPlatform`, understanding it forces the entire BOM |
| Library/SDK published to multiple consumers | Prefer `platform` or scoped constraints; be cautious with `enforcedPlatform` |
| Multiple modules sharing version management | Use a shared convention plugin or `java-platform` project; avoid accidental per-module BOM differences |
| Must override one module to fix a bug | Inspect dependency graph, use appropriate constraint/rule or plugin override; avoid forcing the whole BOM unnecessarily |
| Want faster builds with fewer plugins | Spring Boot notes Gradle native BOM support is generally faster than the Spring plugin |
| Need to adjust versions via BOM-published properties | `io.spring.dependency-management` directly supports this |

These recommendations depend on **Gradle version**, **Spring Boot version**, **publishing strategy**, and **dependency graph**. Nothing automatically guarantees every pair of dependencies is compatible; always run tests after overriding versions.

## 12. Common Mistakes

**Mistake 1: Applying only the Spring Boot Gradle plugin and assuming the BOM is auto-imported.** The Boot plugin auto-imports `spring-boot-dependencies` only when `io.spring.dependency-management` is present; if choosing native, declare `platform(...)`/`enforcedPlatform(...)` explicitly.

**Mistake 2: Applying `io.spring.dependency-management` without the Boot plugin, then omitting all dependency versions.** The plugin needs an imported BOM or declared managed versions. In library modules without the Boot plugin, import the BOM manually if needed.

**Mistake 3: Setting `ext['slf4j.version']` and expecting `platform(...)` to update.** Property overrides are a Spring plugin feature, not how native platforms read BOMs. Use Gradle constraints/rules when using native support.

**Mistake 4: Assuming `platform` always preserves the exact BOM version.** A transitive dependency with a higher requirement can cause Gradle to pick another version; run `dependencyInsight` to see why.

**Mistake 5: Using `enforcedPlatform` in a public library without considering consumers.** Forced versions can propagate and conflict with consuming applications' dependencies.

**Mistake 6: Adding the BOM only to `implementation` and assuming every configuration is managed.** Check configuration inheritance for annotation processors, custom test suites, custom tasks, or other modules.

**Mistake 7: Specifying a direct version alongside a BOM without checking conflicts.** A version written in `implementation("group:module:version")` is not necessarily the **final** version. It may be upgraded or forced depending on the graph and management mechanism.

**Mistake 8: Changing a BOM or version property and assuming published artifacts reflect it accurately.** Inspect the generated `pom.xml` and `.module`, how `api`/`implementation` are exposed, and test from a sample consumer.

**Mistake 9: Confusing a version catalog with a BOM.** Catalogs supply convenient declaration aliases/versions; BOMs/platforms supply constraints participating in transitive resolution. Both can be used together, yet are not interchangeable.

**Mistake 10: Troubleshooting by adding all three mechanisms at once.** Combining the Spring plugin, `platform`, and `enforcedPlatform` makes behavior hard to understand. Pick one primary strategy, then add targeted constraints when needed.

## 13. Practical Verification Checklist

1. Determine whether the module is a **Spring Boot application** or a **library**; check whether `org.springframework.boot` is applied.
2. Choose the management mechanism: Spring plugin, native `platform`, or native `enforcedPlatform`.
3. Verify the BOM version matches the Spring Boot version in the build; prevent modules from accidentally using different Boot versions.
4. Confirm configurations needing management have the BOM/managed versions attached in the right scope.
5. Run `./gradlew dependencies --configuration runtimeClasspath`, and `dependencyInsight` for at least one key module.
6. If overrides exist, justify why; check all related modules, run unit/integration tests, and verify runtime.
7. If publishing a library, inspect Maven POM/Gradle Module Metadata and test consuming the artifact.
8. Check the plugin/Gradle/JDK support matrix when upgrading versions; avoid copying tutorial versions verbatim into a project running a different setup.

### Official Documentation for Reference

- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Gradle User Manual — Platforms](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle User Manual — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
- [Spring Dependency Management Plugin — Reference](https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/)
- [Gradle User Manual — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html)

**Takeaway:** `io.spring.dependency-management` fits Maven-like BOM management and property customization; `platform` lets Gradle mediate versions via constraints; `enforcedPlatform` forces BOM versions and can affect consumers. Always choose based on **desired version control**, **dependency graph scope**, and **artifact consumers**, then verify actual versions with `dependencyInsight`.