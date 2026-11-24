# Reading dependency:tree, dependencies, and dependencyInsight to Explain Selected Versions

## Learning Objectives

In a Spring Boot application, you might declare just one starter or library while the build downloads dozens of other libraries. Sometimes `pom.xml` or `build.gradle` states version A while the application actually runs with version B; sometimes no version is written anywhere yet the build still succeeds. To explain why, you must read the **resolved dependency graph**, not just declaration lines.

After this lesson, you will be able to:

1. Run **Maven `dependency:tree`** to see direct libraries, transitive libraries, and selected versions.
2. Run **Gradle `dependencies`** to view dependencies under specific configurations such as `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath`.
3. Run **Gradle `dependencyInsight`** to answer: who requested this library, which version was requested, which version was selected, and **why**.
4. Explain the roles of the **Spring Boot BOM**, `dependencyManagement`, Gradle platforms/constraints, directly declared versions, and conflict resolution.
5. Investigate real-world issues such as wrong library versions being selected, multiple paths pulling the same library, missing runtime dependencies, and failed dependency resolution.

This lesson focuses on **reading reports and evidence-based reasoning**. Dependency names, versions, and paths in examples are explicitly marked **simulated** when not taken from a live project run; final answers for your project must be confirmed by running the commands in that environment.

## 1. Mental Model: Declared, Requested, Managed, Resolved

Imagine project `app` directly declares `feature-a` and `feature-b`. Both libraries declare `common-lib` at different versions:

```text
app
├── feature-a:1.0
│   └── common-lib:2.0
└── feature-b:1.0
    └── common-lib:3.0
```

This is the **initial requested graph**, not the final result. The build tool must decide whether to select `common-lib:2.0`, `3.0`, or fail; the answer depends on Maven vs. Gradle, BOM-managed versions, constraint/force/exclusion rules, and classpath configuration.

| Term | Meaning | How to Find |
| --- | --- | --- |
| **Direct dependency** | Declared directly by the project in `dependencies` / `<dependencies>` | Read the build file and top-level entries in reports |
| **Transitive dependency** | Pulled in through another dependency | Inspect deeper branches in the dependency tree |
| **Requested version** | Version or version range asked for by a dependency/constraint | Left side of `2.0 -> 3.0` in Gradle; read requesting paths |
| **Managed/constrained version** | Version from BOM, `dependencyManagement`, Gradle constraint, or rule | Inspect effective POM, BOM, insight/selection reasons |
| **Selected/resolved version** | Version chosen by the build tool for **a specific graph/configuration** | Maven `dependency:tree`; Gradle `dependencies` and `dependencyInsight` |
| **Classpath** | Set of libraries serving a purpose like compile, runtime, or test | Maven scopes; matching Gradle `--configuration` |

**Three questions to keep separate:** (1) who **brings** the library into the graph, (2) who **places version requests**, and (3) which rule causes **a specific version to be selected**. Seeing a dependency in a BOM answers only **version management**; it does not prove the library is on the classpath.

### Why Inspect by Classpath?

A dependency may exist in tests yet be absent at runtime; compile-time libraries can differ from libraries packaged to run. Maven uses `scope` (e.g., `compile`, `runtime`, `test`, `provided`); Gradle uses configurations and classpaths such as `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath`. The exact same `group:artifact` coordinates can resolve differently in different contexts.

When asking "**which version is actually used?**", always specify **module + configuration/classpath + build mode** before answering.

## 2. Maven: Running and Reading `dependency:tree`

### Basic Command

In the root directory containing `pom.xml`, run Maven Wrapper:

```bash
./mvnw dependency:tree
```

Windows PowerShell:

```powershell
.\mvnw.cmd dependency:tree
```

This invokes the `tree` goal of the **Maven Dependency Plugin**, printing the project's resolved dependency tree. Use the Wrapper to avoid Maven version mismatches between developer machines and CI. The first run may need to download plugins and dependencies from configured repositories.

**Simulated output** for an application with two branches:

```text
[INFO] com.example:demo:jar:0.0.1-SNAPSHOT
[INFO] +- com.example:feature-a:jar:1.0:compile
[INFO] |  \- org.example:common-lib:jar:2.0:compile
[INFO] \- com.example:feature-b:jar:1.0:compile
```

All `com.example` / `org.example` coordinates in the tree are **hypothetical for explanation**, not claims that real artifacts exist. In `org.example:common-lib:jar:2.0:compile`:

- `org.example` is `groupId`, `common-lib` is `artifactId`.
- `jar` is the artifact type.
- `2.0` is the **version displayed in the resolved tree**.
- `compile` is the Maven scope in this project.
- `+-`, `\-`, and indentation show the **path pulling the dependency in**, not program execution order.

Standard output may **omit versions discarded due to conflicts**. Therefore, seeing `common-lib:2.0` alone is not enough to conclude "only one library requested it"; the `feature-b` branch may have requested another version and been omitted from the winning tree.

### Filtering to Reduce Noise

```bash
# Inspect branches related to a single artifact
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api

# Inspect only runtime-scoped dependencies
./mvnw dependency:tree -Dscope=runtime

# Include omitted nodes from conflicts if supported by the plugin
./mvnw dependency:tree -Dverbose

# Write output to a file to attach to technical reports
./mvnw dependency:tree -DoutputFile=dependency-tree.txt
```

`-Dincludes` takes a Maven coordinate pattern and filters **the report**, without removing other libraries from the build. For instance, `org.slf4j:slf4j-api` is just an example target; if the app does not use SLF4J, no matches appear.

`-Dverbose` on the Maven Dependency Plugin can include **omitted** nodes in the report, such as conflict/duplicate details (formatting and detail depend on plugin version). If your plugin or build does not output expected details, check the running `maven-dependency-plugin` version; do not assume older versions produce identical output. When machine-readable output is needed, newer plugin versions support `-DoutputType=json`; verify your actual plugin version rather than assuming JSON exists everywhere.

In PowerShell, to prevent the shell from splitting arguments with special characters, write `.\mvnw.cmd dependency:tree "-Dincludes=org.slf4j:slf4j-api"`.

### Selecting the Right Maven Module

A multi-module Maven repository can produce **multiple distinct trees**. Run from the application module's `pom.xml` directory or select the module from the reactor, e.g.:

```bash
./mvnw -pl :demo dependency:tree
```

In this example, `demo` must be an actual `artifactId` in the reactor. Never inspect a library module's tree and assume it represents the application module's runtime classpath.

## 3. Why Does Maven Select a Particular Version?

### Nearest Definition Rule

When **no other version management governs the outcome**, Maven uses **dependency mediation** based on **closest path to the root**: the dependency version with the shortest path from the project wins. If two paths have equal depth, the **first** declaration wins.

Given the simulated graph:

```text
demo
├── feature-a:1.0  ------> common-lib:2.0  (depth 2)
└── feature-b:1.0  ------> common-lib:3.0  (depth 2)
```

If `feature-a` appears before `feature-b` in `pom.xml` and no relevant `dependencyManagement` exists, **Maven can pick `common-lib:2.0`** at equal depth under "first declaration wins." If the project directly declares `common-lib:3.0`, that direct edge is closer to root than both transitive paths and affects the result. Never assume Maven defaults to "picking the highest version."

### Role of `dependencyManagement` and BOM

A Spring Boot Maven project usually inherits `spring-boot-starter-parent` or imports the `spring-boot-dependencies` BOM into `dependencyManagement`. The BOM provides a set of **managed** versions for many libraries. When a matching dependency appears in the graph without a higher-precedence declaration/override, Maven fills in or selects the managed version.

Snippet **illustrating the BOM's role**, not a complete POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-core</artifactId>
    </dependency>
</dependencies>
```

`4.1.2` is merely an **example Spring Boot version**; read the real version from your project POM. You do not need to declare `spring-core` directly if another dependency pulls it in; the snippet illustrates "no version specified, yet BOM can manage it." A BOM **does not automatically place all listed dependencies into the application**.

Precedence relationships to remember:

- A version declared **explicitly on a direct dependency** in the project's POM can govern the version used instead of the managed value.
- `dependencyManagement` in the effective POM can **determine the version of transitive dependencies**, overriding standard nearest mediation.
- `dependencyManagement` in the current POM can override inherited management configuration; when importing multiple BOMs with overlapping entries, import order and direct `dependencyManagement` entries affect the result. Always inspect the **effective POM** instead of guessing from file order alone.
- `exclusions`, `optional`, `scope`, and active profiles can change **whether a node exists** before version selection is even evaluated.

### Locating Where Maven Actually Manages Versions

```bash
# View POM model after applying parent, profiles, and inherited management
./mvnw help:effective-pom -Doutput=effective-pom.xml

# If explaining why a specific profile alters dependencies
./mvnw help:active-profiles

# Cross-check actually used dependency
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
```

`effective-pom.xml` is an analysis output file. Look inside it for `<dependencyManagement>`, `groupId`/`artifactId` coordinates, versions, and related declarations. **Finding a version in the effective POM only proves management exists**, not that the dependency appears on the classpath; combine it with `dependency:tree`.

**Distinguish plugins:** project `dependencyManagement` does not configure dependency versions **for Maven plugins**. Plugins have their own classpaths. If the question is about a build plugin, reading the application dependency tree alone may be insufficient.

## 4. Gradle: Running `dependencies` on the Right Configuration

In a Gradle project, from the directory containing `gradlew`, `settings.gradle[.kts]`, and `build.gradle[.kts]`:

```bash
# List major configurations and dependencies of the project
./gradlew dependencies

# Dependency set for running the Java/Spring Boot app
./gradlew -q dependencies --configuration runtimeClasspath

# Dependency set for compiling
./gradlew -q dependencies --configuration compileClasspath

# Dependency set for test runtime
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Windows PowerShell uses `.\gradlew.bat` instead of `./gradlew`. Configuration names depend on plugins/languages/modules; the names above are **standard when applying the Java plugin**, not guaranteed on every Gradle project.

Running `./gradlew dependencies` alone is not always suitable for drawing conclusions about application versions, since the report prints many configurations, unresolvable configurations, and test-only dependencies. When investigating **runtime**, explicitly pass `--configuration runtimeClasspath`.

### Reading Symbols in Gradle Trees

**Simulated** output for a scenario where a library is requested at 2.0 yet selected at 3.0:

```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- com.example:feature-a:1.0
|    \--- org.example:common-lib:2.0 -> 3.0
\--- com.example:feature-b:1.0
     \--- org.example:common-lib:3.0
```

`com.example`/`org.example` coordinates are illustrative only. Interpretation:

- `2.0 -> 3.0`: a path requested version **2.0**, and Gradle **selected 3.0** in the queried configuration.
- The `common-lib:3.0` line under `feature-b` indicates another path requesting that version.
- Results apply strictly to `runtimeClasspath` of the **current project**; do not assume other configurations also select 3.0.

Other symbols per Gradle documentation:

| Symbol | Meaning |
| --- | --- |
| `x -> y` | Requested version `x`, actually selected `y` |
| `(*)` | Subtree was already expanded elsewhere, so it is not repeated in full |
| `(c)` | **Constraint** participating in version management; this line alone does not pull the dependency in |
| `(n)` | Dependency or configuration **not resolvable** in this report context |
| `FAILED` | A requested edge could not be resolved; check the cause above/in logs |

**Do not mistake `(c)` for a second library:** it is constraint metadata. Nor should you read `(*)` as "dependency skipped"; it only suppresses duplicate printing of an already-shown subtree.

### Gradle Multi-Project and Non-Resolvable Configurations

In multi-module builds, query the exact project:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

`:app:` is an **example** module name; substitute your real project path. `implementation`, `api`, or `testImplementation` are normally **declaration buckets**, not directly resolvable dependency reports. If running `--configuration implementation` reports it cannot be resolved, use `compileClasspath`, `runtimeClasspath`, or the appropriate resolvable configuration.

To inspect dependencies for **running Gradle plugins** rather than **application** dependencies, use a different task:

```bash
./gradlew buildEnvironment
```

Do not treat `buildEnvironment` as evidence for Java runtime dependencies. In configurations with dependency resolution failures, reports may be partial; distinguish "no dependency" from "could not resolve dependency."

## 5. Gradle: Using `dependencyInsight` to Answer **Why**

`dependencies` gives you the **big picture**. Once you know the `group:module` to investigate, `dependencyInsight` traces requesting paths and **version selection reasons** inside **a single configuration**.

```bash
# Analyze a specific module on the runtime classpath
./gradlew -q dependencyInsight \
  --dependency org.slf4j:slf4j-api \
  --configuration runtimeClasspath
```

In Windows PowerShell, put it on one line to avoid bash line-continuation syntax:

```powershell
.\gradlew.bat -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

If `org.slf4j:slf4j-api` is absent from the app's `runtimeClasspath`, the report may find nothing; that is evidence **for the queried configuration**, not proof the library is absent from every configuration. `--dependency` accepts `group:name` or a partial name; pass full coordinates to avoid matching multiple modules unintentionally.

Useful flags:

```bash
# Collapse to a single path pulling the dependency in (when multiple paths exist)
./gradlew -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath --single-path

# Target a specific subproject
./gradlew :app:dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

### What Does an Insight Report Tell You?

**Abbreviated, simulated** output example:

```text
org.example:common-lib:3.0
   Selection reasons:
      - By conflict resolution: between versions 3.0 and 2.0

org.example:common-lib:3.0
\--- runtimeClasspath

org.example:common-lib:2.0 -> 3.0
\--- com.example:feature-a:1.0
     \--- runtimeClasspath
```

Do not treat this as a real repo log; real Gradle output may include variant/attribute tables and multiple distinct paths. Key elements to read:

1. `org.example:common-lib:3.0` at the top states the **selected version**.
2. `Selection reasons` explains **mechanisms** that participated in picking the version.
3. The trees below show **which paths requested** the module.
4. `2.0 -> 3.0` indicates the 2.0 request was not kept as-is.
5. Another configuration can produce different output; always record full `project + configuration` when reporting.

### Selection Reasons to Recognize

| `Selection reasons` or Marker | Explanation |
| --- | --- |
| `By conflict resolution` | Multiple version requests existed; the conflict resolver picked one version |
| `By constraint` | A constraint/BOM/metadata constrained or contributed to selection |
| `Forced` | Forced via a mechanism like `enforcedPlatform` or a `force` rule |
| `Selected by rule` | A resolution rule influenced the selection |
| `By ancestor` | A strict requirement (`strictly`) on an ancestor path affected the version |
| `Was requested` | Direct/explicit dependency request or declared `because(...)` rationale |
| Variant/attributes | Explains which **artifact variant** matched the consumer; distinct from version alone |

Not every run displays all rows above. `Selection reasons` can list **multiple reasons**. When you see `By constraint`, trace where the constraint came from; when you see `Forced`, check who forced it and why. Never conclude "the Spring Boot BOM forced this version" merely because a BOM appears in the graph.

## 6. Maven and Gradle Can Pick Differently on the Same Graph

Using the same hypothetical model:

```text
app
├── feature-a:1.0 -> common-lib:2.0
└── feature-b:1.0 -> common-lib:3.0
```

Assuming **no** BOM/constraints/force/exclusions/other direct versions:

| Question | Maven | Gradle |
| --- | --- | --- |
| Typical rule on version conflict | Picks path **closest to root**; at equal depth, first declaration wins | Typically picks the **highest version** among acceptable requests |
| Example outcome if `feature-a` declared first, equal depth | `common-lib:2.0` | `common-lib:3.0` |
| Primary report | `dependency:tree` | `dependencies --configuration ...` |
| To explain conflicts | `-Dverbose` (if plugin supports), `effective-pom`, tree branches | `dependencyInsight --dependency ... --configuration ...` |
| How managed versions interact | `dependencyManagement` / Maven BOM can override nearest | Platform/BOM, dependency constraints, rules, force, and rich versions participate in resolution |

**Do not turn this table into an absolute rule.** In Gradle, `strictly`, `reject`, `enforcedPlatform`, `force`, or resolution rules can yield lower versions, higher versions, or resolution failure due to incompatible constraints. In Maven, BOMs and direct declarations can alter the selected version away from nearest. That is why **current reports matter more than guessing algorithms from memory**.

## 7. Impact of the Spring Boot BOM in Both Build Systems

### Maven: Version Management via Parent or Imported BOM

In a Maven project, the Spring Boot parent or a BOM imported into `dependencyManagement` controls versions of Spring Boot-managed coordinates. A dependency declared **without `<version>`** still resolves thanks to the managed version. If unmanaged and lacking an applicable version elsewhere, Maven reports a missing version error.

Workflow to prove "the BOM picked version X":

1. Use `dependency:tree` to find the **resolved version and path** of the artifact.
2. Use `help:effective-pom` or effective POM/BOM to verify the **managed version**.
3. Check whether a direct dependency sets `<version>`, whether local `dependencyManagement` overrides it, and whether profiles apply.
4. Conclude from **both resolution output and management config**, avoiding claims like "the BOM pulled in the dependency" if it is only in the management list.

### Gradle: Two Common Management Approaches

**Approach A: `io.spring.dependency-management` plugin.** When applied alongside the Spring Boot Gradle plugin as supported, the plugin imports the `spring-boot-dependencies` BOM matching the Spring Boot version. Managed dependencies can omit versions; the plugin handles management and overrides according to its model.

**Approach B: Gradle's native BOM support.** Illustrative **Groovy DSL snippet**, assuming the build applies Java/Spring Boot plugins and resolves `SpringBootPlugin.BOM_COORDINATES`:

```groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

This is a **partial configuration**, not a complete `build.gradle`. With Gradle native BOM support, `platform(...)` creates **dependency constraints** (typically soft recommendations/constraints), so if another dependency asks for a higher version without strict locking, Gradle can select a version different from the BOM value. `enforcedPlatform(...)` is stricter and can force BOM versions; use it intentionally as it can affect consumers and compatibility.

**Common pitfall:** applying the Spring Boot Gradle plugin alone **is not enough to assume** dependencies are version-managed as in Approach A. Check whether the project applies `io.spring.dependency-management` or uses `platform`/`enforcedPlatform`, custom constraints/rules. Read `dependencyInsight` to see the **actual chosen version** instead of inferring from BOM lines alone.

### Example Investigation Path for a Spring Boot Starter

If an application has a starter containing or pulling in a logging library, first locate the exact dependency in `runtimeClasspath`:

```bash
# Maven
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api

# Gradle
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

Next inspect the project's management layer: Maven effective POM/BOM; Gradle `platform`, dependency management plugin, version constraints, and resolution rules. **Do not hardcode a guessed SLF4J version** into your conclusion: it depends on Spring Boot version, concrete dependencies, configuration, and project overrides.

## 8. Real-World Investigation in Three Steps

Suppose you hit a compatibility error and suspect `org.example:common-lib` got the wrong version. These coordinates are **illustrative only**. Answer clearly:

**Step 1 – What is selected, and in which context?**

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.example:common-lib
```

Gradle:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
```

Record the project/module, configuration or scope, full coordinates, and displayed version.

**Step 2 – Who pulled it in, and why was that version chosen?**

Maven:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.example:common-lib
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Gradle:

```bash
./gradlew -q dependencyInsight --dependency org.example:common-lib --configuration runtimeClasspath
```

Trace paths from direct dependencies to the target dependency. In Maven, check nearest definition, dependency management, and direct versions. In Gradle, read `x -> y` lines along with `Selection reasons` and constraints/BOM/rules.

**Step 3 – Verify presence at runtime/test time**

Do not stop after finding a version in `testRuntimeClasspath` and claim it exists in the production runtime. For Spring Boot, check the executable archive and actual classpath when needed; compare the runtime report against packaged archive contents and logs if you suspect a dependency was excluded or packaged differently. In multi-module Gradle builds, target `:module:dependencyInsight`.

### Evidence-Backed Conclusion Template

> In module `:app`, configuration `runtimeClasspath` selects `org.example:common-lib:3.0`. Branch `feature-a` requested `2.0` and was upgraded to `3.0`. `dependencyInsight` reports `By conflict resolution` and also shows branch `feature-b` requesting `3.0`. Therefore this is a case of version conflict resolution in the runtime configuration, **not evidence that the Spring Boot BOM forced `3.0`**.

The above is a **hypothetical conclusion template** matching the simulated example; use it in a real report only when your own project's CLI output produces those exact lines.

## 9. Common Analysis Mistakes

| Hasty Claim | Why It's Wrong / Proper Check |
| --- | --- |
| "POM/build script says A, so A definitely runs" | Dependency management, BOMs, transitives, and constraints/rules all intervene. Check the **resolved tree** per classpath. |
| "Maven always picks the newest version" | Maven uses nearest/first-at-equal-depth unless governed by management rules. |
| "Gradle always picks the highest version" | Only the common default for ordinary conflicts; platforms, strict constraints, enforced platforms, and force/rules can change it. |
| "If the BOM lists a library, the app definitely downloads it" | BOMs/constraints generally only manage versions when a dependency is actually requested. |
| "`(c)` in Gradle is a second JAR" | `(c)` denotes a constraint, not an added dependency. |
| "`(*)` means the dependency is absent" | `(*)` only indicates a repeated subtree was not expanded again. |
| "`2.0 -> 3.0` is Maven changing a dependency" | That notation is typical of Gradle `dependencies`/insight; verify which tool produced the report. |
| "Not in `runtimeClasspath` means the library isn't used anywhere" | It may live in `testRuntimeClasspath`, compile-only, buildscript, or another project. |
| "`dependencyInsight` needs no configuration flag" | Pass `--configuration` when investigating; some plugins have defaults, yet never rely on that for runtime analysis. |
| "Seeing `Selected by rule` means the BOM did it" | Rules can come from build scripts/plugins; locate the rule's source. |
| "Seeing `Forced` means I should force my desired version to fix it fast" | Forcing can cause API/ABI mismatches. Find the root cause and check compatibility/tests first. |
| "Changing one version updates every module/configuration" | Maven modules and Gradle configurations can have different management models/rules. |
| "`Could not resolve` means the dependency doesn't exist" | Could be offline/cache, repository, authentication, metadata, TLS, version constraints, or genuinely missing artifact. Read the cause. |

### When Checking Why a Dependency Is Missing from Reports

1. Confirm the command ran on the **right module**.
2. Check whether the dependency is declared only in **test**, compile-only, annotation processor, or buildscript.
3. Check `exclusions`/`optional`/Maven scopes, Gradle dependency constraints, capabilities/variants, and profiles.
4. If resolution failed, do not trust an incomplete tree as the final list.
5. If a dependency lost a conflict, inspect omitted/losing requests (`-Dverbose` if supported in Maven; `dependencyInsight` in Gradle).
6. Check whether you ran the **repo's Maven/Gradle Wrapper** or another project whose build files changed since the last run.

## 10. Hands-On Exercise: Explain the Version, Don't Just Screenshot Output

Use **an existing Spring Boot Maven or Gradle project** (matching the project's build system).

**Part A – Gather Evidence:**

1. Pick a real dependency present on the classpath, such as a logging or JSON library pulled in by a starter. Record its exact `group:artifact` coordinates.
2. Inspect `pom.xml` or `build.gradle[.kts]`: is that dependency declared directly or only pulled via a starter? Does it specify an explicit version?
3. Run Maven `dependency:tree` or Gradle `dependencies --configuration runtimeClasspath`. Record **module**, **classpath**, **path**, and **actual selected version**.
4. For Maven, run `dependency:tree -Dverbose` (if supported) and `help:effective-pom` to trace the managed version source. For Gradle, run `dependencyInsight --dependency ... --configuration runtimeClasspath`, recording `Selection reasons` and any `x -> y` transitions.
5. Check which Spring Boot parent/BOM, Gradle platform, or dependency management plugin the project actually applies.

**Part B – Explain the Cause in Complete Sentences:**

- "Library X appears because dependency Y pulls it in via path ...".
- "In module ..., configuration/runtime scope ..., the requested version is ...; the final version is ...".
- "Evidence of the final version comes from command ...".
- "Evidence of the selection rule is at ... (nearest/BOM/direct/constraint/conflict/rule)...".
- "I verified whether test and runtime match or differ using ...".

**Part C – Controlled Experiment (on a practice branch):**

Create a scenario with two different version requests for the same module or change a given constraint. Re-run tree/insight and record **before -> after**. Never force a version just to make the exercise "pass"; dependency changes can break runtime. When finished, revert practice edits unless intended for the codebase.

**Completion criteria:** someone reading your report can re-run your commands to verify **who pulled the library in**, **requested versions**, **selected version**, **configuration/classpath**, and **selection reason**. A screenshot of `dependency:tree` or `dependencies` without explaining the mechanism is incomplete.

## Official Documentation for Reference

- Maven Dependency Plugin – `dependency:tree`, filtering, `-Dverbose`, and output formats: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Maven – Dependency Mechanism (nearest definition, dependency management, BOM): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle – Viewing and Debugging Dependencies (`dependencies`, `dependencyInsight`, symbols, and selection reasons): https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle – Dependency Constraints and Conflict Resolution: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
- Spring Boot – Managing Dependencies with Gradle (dependency-management plugin or native BOM): https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html

**Takeaway:** a reliable answer to "why was this version selected?" always pairs **resolution output** with **request sources and management rules**, in the **exact module and classpath**.