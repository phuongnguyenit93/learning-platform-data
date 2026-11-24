# Excluding Dependencies, Handling Optional Dependencies, and Avoiding Missing Runtime Libraries

## 1. The Problem to Solve

In a Spring Boot project, a single dependency can pull in many **transitive dependencies**. Sometimes a library is unnecessary, causes version conflicts, or ships an unsuitable implementation; then an **exclusion** is needed. Sometimes a library author wants an integration feature to activate only if consumers explicitly opt in with a supporting library; Maven provides the **optional** flag. And sometimes builds/tests succeed while production runs fail with missing classes because the **runtime classpath** differs from compile/test classpaths or packaging omitted a needed dependency.

Three concepts to keep distinct:

| Mechanism | What does it decide? | What does it NOT mean? |
|---|---|---|
| Exclusion | Stops pulling a transitive dependency along **the specified dependency path** | Deletes that artifact from every path or automatically replaces it |
| Maven `<optional>true</optional>` | Whether projects **depending on your library** automatically receive that dependency | That the optional library is removed from the declaring module's own classpath |
| Scope/configuration + packaging | Which compile, test, and runtime classpaths and artifacts receive the dependency | That compiling cleanly guarantees runtime has every class |

Visualize:

```text
Application A
├── library B
│   ├── library C
│   └── library D
└── library E
    └── library D

A excludes D via branch B:
A -> B -X-> D
A -> E ---> D    (D can still be selected via E)
```

**Practical rule:** exclude only once you know where the library enters, why it is unneeded or what should replace it, and verify both the dependency graph **and** the final runnable artifact.

## 2. Understanding Dependencies at Each Stage

A class can exist at compile time yet be absent at runtime. That is why **`NoClassDefFoundError`** or **`ClassNotFoundException`** commonly appear after misconfiguring scope, optional flags, or exclusions.

### Maven Scopes

| Scope in `pom.xml` | Compile classpath | Standard Maven runtime classpath | Meaning |
|---|---|---|---|
| `compile` (default) | Yes | Yes | Needed to compile and run |
| `runtime` | No | Yes | e.g., a JDBC driver loaded dynamically at runtime |
| `provided` | Yes | No | Use only if the runtime environment genuinely supplies it |
| `test` | Not for main code | Not for main app | Only for compiling/running tests |

These are **Maven classpath rules**, not a promise that every packaging plugin treats them identically. For instance, **Spring Boot Maven Plugin `repackage` has special rules for `provided` dependencies**: executable archives may include them; for executable WARs, `provided` dependencies are placed in `WEB-INF/lib-provided` to avoid colliding with the servlet container. So never look at scope alone—inspect the actual JAR/WAR layout.

### Common Gradle Configurations

| Configuration | Main Compile | Main Runtime | When to Use |
|---|---|---|---|
| `implementation` | Yes | Yes | Application uses the library at compile and runtime |
| `runtimeOnly` | No | Yes | Drivers or providers needed only when running |
| `compileOnly` | Yes | No | APIs genuinely supplied by runtime/another environment, or certain compile-time tools |
| `testImplementation` | Test compile only | Test runtime only | Unit/integration testing libraries |

`api` from the `java-library` plugin exposes a dependency in consuming modules' compile API; a library's `implementation` does not appear on library consumers' **compile classpath**, yet still normally participates in their runtime. Do not think of `implementation` as "never transitive": the key distinction is **separating compile API from runtime**.

If application code directly requires a library at runtime, declare it directly rather than hoping another starter/library pulls it in. BOMs and `dependencyManagement` only manage versions; they **do not add dependencies** to the classpath by themselves.

## 3. Maven Exclusions: Removing the Right Dependency on the Right Branch

Suppose:

```text
app
└── library-a
    └── legacy-json-lib
```

If `library-a` pulls in `legacy-json-lib` which your application does not use (or has replaced with a compatible library), place an exclusion **inside the dependency declaration for `library-a`**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>library-a</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>legacy-json-lib</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

This is an **illustrative XML snippet**, not a standalone `pom.xml`; `com.example` coordinates merely describe the relationship. In Maven, exclusions specify `groupId` + `artifactId` and attach to the **dependency branch** being trimmed. They do not require the excluded artifact's version; if the same dependency enters via another branch, that branch can still bring it back.

First trace the exact path:

```bash
# Maven project with wrapper:
./mvnw dependency:tree

# Focus on the target artifact; substitute real coordinates
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-logging

# Inspect runtime-scoped dependencies via Maven Dependency Plugin filter
./mvnw dependency:tree -Dscope=runtime
```

In Windows PowerShell, use `.\mvnw.cmd` instead of `./mvnw`. If the project has no wrapper, use `mvn`. `dependency:tree` displays resolved dependencies; read parent branches to locate **where to place the exclusion**, and re-run after editing.

### Real-World Example: Swapping the Logging Starter in Spring Boot

In a **Spring Boot 3.x Maven project**, one way to switch from the default logging starter to Log4j2 is:

```xml
<dependencies>
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
</dependencies>
```

This snippet assumes `pom.xml` already has `spring-boot-starter-parent` or the Spring Boot BOM managing starter versions. It illustrates **excluding the unwanted piece and adding the replacement**. If other dependencies also pull in `spring-boot-starter-logging`, re-inspect the dependency tree and handle those branches accordingly; never assume a single exclusion removes the logging starter everywhere. Verify that only the expected logging provider/implementation remains on the runtime classpath.

Do not mechanically exclude `slf4j-api` when swapping logging: logging APIs and logging implementations/providers are separate components. Excluding the wrong one can let the app compile while failing class loading at runtime.

## 4. Gradle Excludes: Same Goal, Different Syntax

In `build.gradle` using **Groovy DSL**, exclude a transitive dependency on a branch:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
```

This assumes the project already configures the Spring Boot plugin, repositories, and dependency version management. `exclude` uses **group + module**; in Gradle, "module" corresponds to `artifactId` for standard Maven modules.

Kotlin DSL equivalent:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-logging"
        )
    }

    implementation("org.springframework.boot:spring-boot-starter-log4j2")
}
```

These are **`dependencies` blocks to insert into an already-configured build file**, not complete `build.gradle[.kts]` files. In Gradle, when a module is excluded on one path while another path still requests it, the outcome depends on the **entire graph and resolution config**. Use diagnostic commands:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-boot-starter-logging
```

On Windows use `gradlew.bat`. If there is no Gradle Wrapper, use an installed `gradle`. Java/Spring Boot plugins normally provide `runtimeClasspath`; projects without the Java plugin or using custom setups must check actual configuration names.

**Avoid global excludes** like `configurations.all { exclude ... }` to "clean up the tree" wholesale. That easily drops a library genuinely needed by another module, causing hard-to-trace runtime failures. Always prefer targeted exclusions on a specific branch and module.

## 5. Maven Optional: Impact on Library Consumers

Maven `<optional>true</optional>` is used when a **library author** supports an opt-in feature. For instance, module `reporting-core` offers PostgreSQL integration, while users calling only basic data processing do not need the PostgreSQL driver.

In **`reporting-core`'s `pom.xml`** (assuming the PostgreSQL version is managed by parent/BOM, or specifying `version`):

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <optional>true</optional>
</dependency>
```

Meaning:

1. **Inside `reporting-core` itself**, the declared dependency still participates in compile/runtime per its scope. `optional` is not a scope and does not remove the dependency from this module's classpath.
2. **In an application `orders-app` depending on `reporting-core`**, the PostgreSQL driver **does not come along automatically** just because `reporting-core` marked it optional.
3. If `orders-app` actually uses PostgreSQL functionality, the app **must declare the driver directly**.

In **`orders-app`'s `pom.xml`** with a parent/BOM managing versions:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>reporting-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Here `com.example:reporting-core:1.0.0` is an illustrative coordinate; a real module is needed to run. `runtime` makes sense when the app uses JDBC via `DriverManager`/Spring JDBC without directly referencing driver classes at compile time.

**Do not confuse `optional` with `exclude`:**

| Situation | Who decides? | Behavior |
|---|---|---|
| `reporting-core` marks PostgreSQL `optional` | Library author | Does not propagate that dependency by default to consumers |
| `orders-app` excludes a dependency via `reporting-core` | Application author | Blocks the dependency along the chosen declared branch |
| `orders-app` declares PostgreSQL directly | Application author | Driver enters the appropriate classpath regardless of `reporting-core`'s optional flag |
| `orders-app` only imports the BOM | Application author | Version may be managed, yet the driver is not added yet |

**`optional` is a propagation rule in Maven metadata.** Gradle has its own variant/feature capability model; do not treat Maven's `optional` as an exact clone of `compileOnly`, `runtimeOnly`, or a single Gradle configuration. When consuming Maven-published libraries from Gradle, inspect Gradle's actual resolved graph rather than assuming mechanically.

When multiple independent optional features exist, designing **separate modules** (`reporting-jdbc`, `reporting-core`...) or explicit feature variants is usually easier to consume and test than overusing `optional`.

### Optional During Spring Boot Packaging

A Spring Boot application is normally the final runnable artifact, not a library imported by many other applications. Therefore, **do not mark dependencies required in production as `optional` just to shrink the executable JAR**. Packaging behavior for optional dependencies also depends on the Spring Boot Maven Plugin version and flags like `includeOptional`; newer versions omit optional dependencies by default. The safe choice is declaring runtime dependencies accurately, configuring the plugin only when truly needed, and **inspecting the archive and running the packaged application**.

## 6. Avoiding Missing Runtime Libraries: Understanding Classpaths Properly

**Compile classpath ≠ runtime classpath ≠ test runtime classpath.** Common causes:

- A dependency was misassigned to `provided`/`compileOnly`, while the runtime environment **does not supply it**.
- A dependency exists only in `test`/`testImplementation`: unit tests have the class, yet the running app lacks it.
- An optional dependency was omitted from the graph when consuming a library; the app forgot to declare the needed feature dependency.
- An exclusion removed a library needed for logic, reflection, serialization, SPI, or auto-configuration.
- A plain JAR does not embed dependencies; running via `java -jar` lacks external classpath entries.
- Docker images/CI jobs grabbed the wrong artifact, omitting runtime libraries or bundling a different version.
- The BOM resolved a different version than expected, causing `NoSuchMethodError` or binary incompatibility.

### Standalone Java 17 Experiment: Compiles Cleanly, Fails at Runtime with Missing Dependency

The following **uses no external libraries and runs on Java 17+**. It simulates an application compiling with a library present, then missing that library on the runtime classpath.

Create two files:

`src/demo/lib/Feature.java`

```java
package demo.lib;

public final class Feature {
    private Feature() {}

    public static String message() {
        return "Feature available";
    }
}
```

`src/demo/app/Main.java`

```java
package demo.app;

import demo.lib.Feature;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Feature.message());
    }
}
```

From the example root, on **Linux/macOS**, run:

```bash
mkdir -p build/lib build/app
javac -d build/lib src/demo/lib/Feature.java
javac -cp build/lib -d build/app src/demo/app/Main.java

# Runtime missing dependency: program fails
java -cp build/app demo.app.Main

# Add lib directory to runtime classpath:
java -cp "build/app:build/lib" demo.app.Main
```

`java -cp build/app demo.app.Main` can fail with `NoClassDefFoundError: demo/lib/Feature` because the JVM cannot find `Feature` at invocation. Do not expect an identical verbatim stack trace across JDK versions. The final command prints exactly:

```text
Feature available
```

In **Windows PowerShell**, replace the `:` classpath separator with `;`, for example:

```powershell
New-Item -ItemType Directory -Force build/lib, build/app | Out-Null
javac -d build/lib src/demo/lib/Feature.java
javac -cp build/lib -d build/app src/demo/app/Main.java

# Dependency present at compile time, missing at runtime:
java -cp build/app demo.app.Main

# Dependency present at runtime:
java -cp "build/app;build/lib" demo.app.Main
```

The final command also prints `Feature available`. If the library is a JAR instead of a directory, the runtime classpath must point to **that JAR**. In Maven/Gradle, scopes/configurations and packaging plugins manage this list of JARs/runtime classpath entries.

### Easily Confused Java Errors

| Error | Interpretation and Initial Check |
|---|---|
| `ClassNotFoundException` | Usually caused by `Class.forName` or a classloader loading a class name not on the classpath |
| `NoClassDefFoundError` | JVM needed a class definition that is missing or failed static initialization; check runtime classpath and static initializer failures |
| `NoSuchMethodError` | Class exists, yet the runtime version lacks a method expected by compiled bytecode; usually a version/binary mismatch |
| `ServiceConfigurationError` or SPI provider not found | Provider/`META-INF/services` configuration missing, missing JAR, initialization error, or improperly packaged |
| `ClassCastException` | Do not assume a missing dependency; may be caused by different classloaders or incompatible types |
| Spring `NoSuchBeanDefinitionException` | No matching bean found; may be due to auto-configuration conditions, component scanning, or configuration—not necessarily a missing JAR |

**Note:** Seeing a library in the dependency tree does not guarantee it is on the running artifact's runtime classpath; check scope, exclusions, post-resolution version, packaging, and classloaders.

## 7. Inspecting What the Spring Boot Artifact Actually Contains

A Spring Boot executable JAR built by `spring-boot-maven-plugin:repackage` or Gradle `bootJar` typically has the layout:

```text
BOOT-INF/classes/  <- application classes and resources
BOOT-INF/lib/      <- packaged dependency JARs
META-INF/
org/springframework/boot/loader/...
```

Exact structure can vary by version and packaging mode; an executable WAR has `WEB-INF/lib` and potentially `WEB-INF/lib-provided`. A standard JAR built by `maven-jar-plugin` or Gradle `jar` typically does **not** embed all dependencies.

Example for a project producing `target/boot-deps-demo-0.0.1-SNAPSHOT.jar`, on Linux/macOS:

```bash
./mvnw clean package
jar tf target/boot-deps-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/'
java -jar target/boot-deps-demo-0.0.1-SNAPSHOT.jar
```

On Windows PowerShell:

```powershell
.\mvnw.cmd clean package
jar tf target/boot-deps-demo-0.0.1-SNAPSHOT.jar | Select-String 'BOOT-INF/lib/'
java -jar target/boot-deps-demo-0.0.1-SNAPSHOT.jar
```

**These are example inspection commands for an artifact with that filename**, working only if the project actually produces that file and configures an executable JAR. Substitute the actual artifact path from your build log on other projects. `jar` ships with the JDK. Do not assume specific runtime output without application code and configuration.

Things to verify:
1. Is the needed dependency **resolved** at the right version at runtime?
2. Inside the executable JAR, is the right JAR under `BOOT-INF/lib/`, unless validly supplied by an external environment?
3. Is the artifact deployed to Docker/VM the exact artifact you just inspected?
4. When running via `java -jar` (or the real image/container), are the code paths requiring that library actually exercised and tested?

**Important Spring Boot nuance:** `repackage` can include `provided` dependencies per plugin rules; executable WARs put them in `WEB-INF/lib-provided`. `includeOptional` and plugin-level exclusions vary by version. Never infer from Maven scope alone whether a dependency is inside `BOOT-INF/lib/`; **the built archive** is the final evidence.

## 8. Safe Workflow Before and After Excluding

### Step 1 — Identify the Root Cause

Before editing POM/Gradle, state the goal clearly: swap logging providers, avoid a vulnerable dependency, drop an unneeded module, or fix a version conflict. If the issue is purely a **version conflict**, **version management via BOM/constraints** is often better than an exclusion. Never use exclusions to mask symptoms before knowing which library is actually loaded.

### Step 2 — Inspect the Resolved Graph

Maven:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
./mvnw help:effective-pom
```

`help:effective-pom` helps inspect the POM after inheritance, profiles, and management configuration. `dependency:tree` filters trace dependency paths. On Windows, use `.\mvnw.cmd` instead of `./mvnw`.

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency postgresql
./gradlew dependencies --configuration testRuntimeClasspath
```

Check **compileClasspath**, **runtimeClasspath**, and **testRuntimeClasspath** when an issue appears in only one stage.

### Step 3 — Make Minimal Edits and State Dependency Responsibility

- If a transitive dependency is unneeded, exclude it **only on the branch pulling it in**.
- If an implementation is being replaced (like a logging provider), add the new implementation explicitly.
- If your library offers an opt-in integration feature, consider `optional` so consumers do not inherit extra modules inadvertently.
- If the application **needs** a dependency at runtime, declare it directly in `compile`/`runtime` or `implementation`/`runtimeOnly` depending on how code uses it.
- Avoid putting production dependencies in `test`/`provided`/`compileOnly` just to make builds look lighter.
- Verify versions through BOM/parent/constraints and Java compatibility; Maven selects versions by mediation rules, while Gradle has its own resolution engine.

### Step 4 — Re-Verify Against the Real Build

1. Re-inspect the resolved dependency tree after edits to confirm which artifacts are **actually selected or omitted**.
2. Run a build with tests: `./mvnw clean verify` or `./gradlew clean build`.
3. Inspect the output JAR/WAR; for a Spring Boot executable JAR, check `BOOT-INF/lib/`.
4. Run the **exact artifact to be deployed**; test the functionality relying on the changed dependency rather than only checking startup.
5. If packaging Docker images, test the built image; ensure build and runtime stages use the exact right artifact.

A test suite relying purely on mocks can miss real runtime dependencies. If swapping a database driver, test a real connection in an appropriate test environment; if swapping a logging provider, check bindings/providers and actual log output.

## 9. Decision Scenarios

| Scenario | What to do? | Why? |
|---|---|---|
| Starter pulls default logging; want Log4j2 | Exclude logging starter on that branch, add Log4j2 starter, check entire graph | Replacing an implementation requires supplying the replacement |
| Your library integrates a database used only by some consumers | Mark dependency `optional` on the library or split out an integration module | Avoid forcing every consumer to carry the driver |
| Application uses a feature from an optional dependency | Declare that dependency directly in the application | Optional dependencies do not propagate to consumers |
| Compiles cleanly, yet runtime misses classes | Check runtime scope/configuration, exclusions, packaging, and deployed artifact | Compile classpath can be broader than runtime |
| Only `NoSuchMethodError` occurs at runtime | Check actual JAR versions and resolution | Likely binary incompatibility, not an entirely missing class |
| Want to enforce a version of a transitively pulled library | Prefer verified BOM/`dependencyManagement`/constraints | Exclusions do not replace version resolution mechanisms |
| Fails in unit tests, yet works in production | Check `test` dependencies and test runtime classpath | Test and application classpaths differ |
| Want to reduce executable JAR size | Find genuinely unused libraries, understand relationships, test after excluding | Deleting arbitrarily breaks features loaded only at runtime |

## 10. Checklist Before Concluding a Fix Is Done

- [ ] Know the exact `groupId:artifactId` (Maven) or `group:module` (Gradle) coordinates of the dependency in question.
- [ ] Know **which branches** bring the dependency in; do not guess from a single direct dependency.
- [ ] If excluding, confirmed no other branch pulls the module back in, or handled those branches too.
- [ ] If an excluded module served a feature, added its replacement or declared it directly where needed.
- [ ] If using Maven `optional`, understand **consumers do not automatically receive the dependency**, while the declaring module can still use it.
- [ ] Scopes/configurations are accurate for compile, test, and runtime; aware of packaging plugin exceptions.
- [ ] Resolved versions align with Spring Boot BOM/JDK with no API conflicts.
- [ ] The real JAR/WAR/image contains required dependencies, runs, and passes tests on critical functionality.
- [ ] Did not treat mere success of `package` as a substitute for runtime testing.

**Summary:** exclusions sever a **transitive dependency path**; `optional` lets **library consumers decide whether to opt into an extra dependency**; scopes/configurations and packaging decide **whether classes exist at runtime**. To fix missing-library errors, trace backward from exception -> runtime classpath -> resolved dependency tree -> POM/Gradle -> final artifact, verifying each change.

### Official Documentation

- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies)
- [Gradle — How to Exclude Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)