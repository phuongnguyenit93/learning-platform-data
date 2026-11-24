# Passing Properties with -P, -D, and Environment Variables in Gradle with Spring Boot

## 1. Three Mechanisms, Three Scopes of Impact

When running Gradle to build or launch a Spring Boot application, developers commonly see three forms:

```bash
./gradlew build -PbuildMode=ci
./gradlew build -Ddemo.trace=on
APP_ENV=staging ./gradlew build
```

All three "pass a value", yet they **are not the same kind of property, are not read from the same place, and do not automatically reach every Java process**. To use them correctly, ask: **does the value control Gradle build logic, the JVM running Gradle, or the Spring Boot application launched by Gradle?**

| Mechanism | Where the value is set | How Gradle build logic should read it | Primarily used for |
| --- | --- | --- | --- |
| `-Pkey=value` | **Gradle project property** | `providers.gradleProperty("key")` | Choosing targets, build variants, non-sensitive URLs, custom task flags |
| `-Dkey=value` | **Java system property of the Gradle JVM** | `providers.systemProperty("key")` | JVM/Gradle tooling, proxies, and tools reading system properties in the build process |
| `KEY=value` in environment | **OS environment variable** of the process invoking Gradle | `providers.environmentVariable("KEY")` | CI metadata, environment endpoints, credentials via secret injection |
| `-Dorg.gradle.project.key=value` | Special **system property syntax** converted by Gradle into a **project property** | `providers.gradleProperty("key")` | Passing a project property through the `-D` channel |
| `ORG_GRADLE_PROJECT_key=value` | Specially prefixed environment variable; Gradle converts it into a **project property** | `providers.gradleProperty("key")` | Project properties/secrets injected by CI |
| `--args='--server.port=9090'` with `bootRun` | **Spring Boot application command-line args** | Spring `Environment`/binding | Runtime Spring Boot configuration |

**Key takeaway:** `-PserverPort=9090` does not automatically become `server.port=9090` inside Spring Boot. `-Dserver.port=9090` on the **Gradle command** sets a system property on the Gradle JVM; `bootRun` normally spawns a **different JVM**, so it does not inherit that property by default either. For the application to see a value, pass it via `bootRun --args`, OS environment variables, `BootRun.systemProperty(...)`, or pass Java/Spring flags when running the executable JAR.

## 2. `-P`: Gradle Project Properties

### 2.1. Syntax and How to Read

Example:

```bash
./gradlew build -PbuildMode=ci
./gradlew :service:bootJar -PtargetEnv=staging
```

Gradle places `buildMode=ci` / `targetEnv=staging` into the **project properties** namespace. In a Kotlin DSL build script:

```kotlin
val buildMode = providers.gradleProperty("buildMode").orElse("local")

tasks.register("showBuildMode") {
    doLast {
        println("buildMode=" + buildMode.get())
    }
}
```

Running `./gradlew -q showBuildMode -PbuildMode=ci` prints:

```text
buildMode=ci
```

If `-PbuildMode` and any other value sources are absent, the result is `buildMode=local`. That is a **script-defined default**, not something Gradle supplies automatically.

Prefer `providers.gradleProperty("key")` for build inputs because it returns a `Provider<String>`: it supports `orElse`, `map`, wiring to task inputs, and tracking by Gradle when used properly. Older APIs like `project.findProperty("key")` still work, but they search the dynamic project model and can match extra properties, extensions, or task names; `providers.gradleProperty` focuses on **build configuration Gradle properties**, making it easier to reason about and compatible with the configuration cache.

### 2.2. Other Ways That Also Create a Project Property

Four typical channels:

```bash
./gradlew showBuildMode -PbuildMode=ci
./gradlew showBuildMode -Dorg.gradle.project.buildMode=ci
ORG_GRADLE_PROJECT_buildMode=ci ./gradlew showBuildMode
```

Or in `gradle.properties`:

```properties
buildMode=ci
```

All four can be read via `providers.gradleProperty("buildMode")`. However, **`-DbuildMode=ci` is not equivalent to `-PbuildMode=ci`**: without the `org.gradle.project.` prefix it is only a system property; `providers.gradleProperty("buildMode")` will not read `-DbuildMode`.

**Special syntax to remember:**
- `-PbuildMode=ci` → project property `buildMode`.
- `-Dorg.gradle.project.buildMode=ci` → also creates project property `buildMode`.
- `-DbuildMode=ci` → Gradle JVM system property `buildMode`.
- `ORG_GRADLE_PROJECT_buildMode=ci` → environment variable interpreted by Gradle as project property `buildMode`.
- `BUILD_MODE=ci` → regular environment variable, read via `providers.environmentVariable("BUILD_MODE")`; does not create project property `buildMode`.

### 2.3. Do Not Confuse Project Properties with Spring Boot Properties

Building with `-Pprofile=dev` does not automatically expose profile `dev` to Spring Boot. `-P` is useful when **build logic** needs to choose artifacts/versions/tasks, or configure `bootRun` to forward values into the application JVM. Conversely, if you simply want to run Spring Boot with profile `dev`, the concise command is usually:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

This sends the argument **directly to the application** through `bootRun`, without needing extra `-P` mapping. When separating build and runtime deployments, keeping runtime secrets/config out of the packaging step is even more important.

## 3. `-D`: Java System Properties of the Gradle JVM

### 3.1. What Does `-D` on the Gradle Command Affect?

```bash
./gradlew build -Ddemo.trace=enabled
```

In `build.gradle.kts`:

```kotlin
val traceMode = providers.systemProperty("demo.trace").orElse("disabled")

tasks.register("showTrace") {
    doLast {
        println("demo.trace=" + traceMode.get())
    }
}
```

Running `./gradlew -q showTrace -Ddemo.trace=enabled` prints:

```text
demo.trace=enabled
```

This system property belongs to **the JVM executing the Gradle build**. Running `-Ddemo.trace=enabled` does not automatically pass that property to other JVMs spawned by Gradle (such as `Test`, `JavaExec`, or `bootRun`). You must configure forwarding onto the specific task; section 8 demonstrates this.

Use `-D` for JVM/Gradle options and plugins that actually read system properties, such as network/proxy settings, build debugging, or `org.gradle.*` Gradle settings. Do not assume every `-D` key is a Spring Boot application configuration key.

### 3.2. `-Dorg.gradle.project.*` Is the Project-Property Exception

```bash
./gradlew -q showBuildMode -Dorg.gradle.project.buildMode=preprod
```

Gradle supports the `org.gradle.project.` prefix to set a **project property**. Here, `providers.gradleProperty("buildMode")` returns `preprod`. This is an intentional exception; not every system property becomes a project property.

You can configure both styles in `gradle.properties`:

```properties
# Direct project property
buildMode=local

# Java system property of the Gradle JVM
systemProp.demo.trace=enabled

# Also a project property due to the special prefix
systemProp.org.gradle.project.deployTier=preprod
```

There is no need to declare all three channels for the same name. Pick a clear default, allow CLI or CI overrides, and check precedence when conflicts arise.

### 3.3. Gradle `org.gradle.*` Settings Differ from Project Properties

Some properties configure Gradle itself:

```properties
# gradle.properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
```

Or, for Gradle properties supporting overrides, use `-Dorg.gradle.caching=true` / `-Dorg.gradle.java.home=/path/to/jdk`. These **configure Gradle**, and do not automatically forward properties into a Spring Boot application. `org.gradle.jvmargs` affects the Gradle daemon JVM, not the heap allocated to `bootRun` or the executable JAR. To configure heap for `bootRun`, configure `JavaExec`/`BootRun` JVM args; for a standalone JAR use `java -Xmx... -jar app.jar`.

## 4. Environment Variables: Two Completely Different Kinds

### 4.1. Standard OS Environment Variables

Example on Linux/macOS:

```bash
export APP_ENV=staging
./gradlew -q showInputs
```

In Gradle Kotlin DSL:

```kotlin
val appEnv = providers.environmentVariable("APP_ENV").orElse("local")

tasks.register("showAppEnvironment") {
    doLast {
        println("APP_ENV=" + appEnv.get())
    }
}
```

`providers.environmentVariable("APP_ENV")` returns the value of the environment variable passed to the Gradle process; if absent, `orElse("local")` supplies the default. `System.getenv("APP_ENV")` can still read it, but the Provider API integrates better with input tracking for the configuration cache and task state.

Note that **environment variable names are normally case-sensitive on Linux**. `APP_ENV` differs from `app_env`; in CI, standardize spelling carefully, especially when moving from Windows to Linux containers.

### 4.2. The Special `ORG_GRADLE_PROJECT_*` Environment Variable

Gradle recognizes variables named by this convention:

```bash
export ORG_GRADLE_PROJECT_buildMode=ci
./gradlew -q showBuildMode
```

Task `showBuildMode` reads it via `providers.gradleProperty("buildMode")` and prints `buildMode=ci` unless overridden by a higher-precedence source. This is a common way for CI to inject **project properties** without putting `-P...` directly on the command line.

Differences:

| Environment variable | Typically read by API | Meaning |
| --- | --- | --- |
| `APP_ENV` | `providers.environmentVariable("APP_ENV")` | Standard OS variable, can be inherited by child processes |
| `ORG_GRADLE_PROJECT_buildMode` | `providers.gradleProperty("buildMode")` | Converted by Gradle into a project property |
| `SPRING_PROFILES_ACTIVE` | Spring Boot `Environment` | Selects active Spring profiles at runtime when passed to the app |
| `SERVER_PORT` | Spring Boot `Environment` | Runtime configuration value for `server.port` |
| `JAVA_HOME` | Gradle/JVM bootstrap | Selects the JDK used to launch Gradle, unless overridden |
| `GRADLE_USER_HOME` | Gradle | Changes the location of the Gradle user home config/cache |

**`ORG_GRADLE_PROJECT_*` is not a magic Spring Boot variable.** For example, `ORG_GRADLE_PROJECT_springProfile=dev` is converted by Gradle into project property `springProfile`; Spring Boot receives a profile only if the `bootRun` task is configured to forward it.

### 4.3. Setting Variables Across Shells

Linux/macOS:

```bash
APP_ENV=staging ./gradlew -q showInputs
ORG_GRADLE_PROJECT_buildMode=ci ./gradlew -q showInputs
```

PowerShell:

```powershell
$env:APP_ENV = "staging"
$env:ORG_GRADLE_PROJECT_buildMode = "ci"
.\gradlew.bat -q showInputs
```

In PowerShell, variables set in the current session persist until changed, cleared, or the session ends; in CI, use job/step-level environment variable mechanisms. In Windows Command Prompt:

```bat
set APP_ENV=staging
set ORG_GRADLE_PROJECT_buildMode=ci
gradlew.bat -q showInputs
```

`./gradlew` is the wrapper script on Unix; on Windows use `gradlew.bat`. Output examples below assume a compatible Gradle Wrapper exists; if none exists yet, generate it with `gradle wrapper` from an installed Gradle, or invoke `gradle` instead of the wrapper.

## 5. Precedence: When the Same Key Is Set in Multiple Places

There is no **single** universal precedence table shared across Gradle project properties, JVM system properties, OS environment variables, and Spring Boot configuration. They belong to distinct namespaces. Evaluate **each key within its own namespace**.

### 5.1. Precedence for Gradle Project Properties

For a project property read via `providers.gradleProperty("buildMode")`, common sources have precedence from highest to lowest:

1. `-PbuildMode=...` on the CLI.
2. `-Dorg.gradle.project.buildMode=...` (or system property with the equivalent prefix).
3. `ORG_GRADLE_PROJECT_buildMode=...` from the environment.
4. Values in `gradle.properties` loaded by Gradle (user home/root/installation in their own order).

For instance, if `gradle.properties` sets `buildMode=local`, the environment sets `ORG_GRADLE_PROJECT_buildMode=ci`, and the command includes `-PbuildMode=manual`, the task reads `manual`.

Specifically regarding **`gradle.properties` files**: user-level `GRADLE_USER_HOME/gradle.properties` normally takes precedence over the build root file, and the Gradle installation file has lower precedence. Whether an API also checks subproject `gradle.properties` files or dynamically assigned extra properties depends on the API; `providers.gradleProperty` focuses on **build-level Gradle properties**, unlike `Project.findProperty`. Do not rely on dynamic parent-project lookup to establish new build contracts.

### 5.2. Precedence for Gradle JVM System Properties

With `providers.systemProperty("demo.trace")`, `-Ddemo.trace=on` on the CLI overrides `systemProp.demo.trace=off` in `gradle.properties`. This is a **system property** and does not mean an environment variable `DEMO_TRACE` will automatically override it.

Multi-project Gradle note: `systemProp.*` lines inside a **subproject**'s `gradle.properties` are not used as Gradle JVM system properties the way root project ones are; place them in root or Gradle user home. If different modules need different configuration, use project properties or task properties instead of expecting each subproject to have its own Gradle JVM.

### 5.3. Spring Boot Has Its Own Runtime Precedence

When multiple sources set `demo.message` for a **Spring Boot application**, common sources typically follow this order:

```text
Application command-line args: --demo.message=from-args
      (higher)
Java system property of app JVM: -Ddemo.message=from-jvm
      (higher)
OS environment variable: DEMO_MESSAGE=from-env
      (higher)
application.properties / application.yml: demo.message=from-file
```

This compares **familiar sources in a typical scenario**, not an exhaustive list of every `PropertySource`: test properties, Devtools, `SPRING_APPLICATION_JSON`, and specialized configurations can alter outcomes. Always distinguish `-Ddemo.message` on the **`java` command** from `-Ddemo.message` on the **`gradlew` command** unless forwarded.

## 6. Standalone Runnable Example: Testing `-P`, `-D`, and Environment Variables Together

Create an empty directory and two files. This example requires only compatible Gradle/JDK; **no Spring Boot plugin is needed** to observe configuration sources.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "gradle-property-lab"
```

**`build.gradle.kts`:**

```kotlin
val mode = providers.gradleProperty("buildMode").orElse("local")
val trace = providers.systemProperty("demo.trace").orElse("disabled")
val environment = providers.environmentVariable("APP_ENV").orElse("unset")

tasks.register("showInputs") {
    group = "help"
    description = "Prints 3 non-sensitive configuration types"
    doLast {
        println("buildMode=" + mode.get())
        println("demo.trace=" + trace.get())
        println("APP_ENV=" + environment.get())
    }
}
```

Run on Linux/macOS:

```bash
APP_ENV=staging ./gradlew -q showInputs -PbuildMode=ci -Ddemo.trace=enabled
```

**Exact stdout of the lines printed by the task:**

```text
buildMode=ci
demo.trace=enabled
APP_ENV=staging
```

In a clean project with none of these variables/properties set, running `./gradlew -q showInputs` outputs:

```text
buildMode=local
demo.trace=disabled
APP_ENV=unset
```

The third line holds only if `APP_ENV` is genuinely absent; existing values from your shell/CI or `gradle.properties` will change the output. `-q` suppresses regular Gradle logs, though if an error occurs or your Gradle version emits warnings, extra messages may still appear in the terminal.

To test the special `-D` form:

```bash
./gradlew -q showInputs -Dorg.gradle.project.buildMode=preprod
```

With other sources absent, output:

```text
buildMode=preprod
demo.trace=disabled
APP_ENV=unset
```

Changing to `-DbuildMode=preprod` reverts `buildMode` to `local` because that is a system property not read by `providers.gradleProperty`. To observe it, add `providers.systemProperty("buildMode")` in the task.

**Groovy DSL equivalent** (replace `build.gradle.kts` with `build.gradle` and use a matching `settings.gradle`):

```groovy
def mode = providers.gradleProperty('buildMode').orElse('local')
def trace = providers.systemProperty('demo.trace').orElse('disabled')
def environment = providers.environmentVariable('APP_ENV').orElse('unset')

tasks.register('showInputs') {
    group = 'help'
    doLast {
        println 'buildMode=' + mode.get()
        println 'demo.trace=' + trace.get()
        println 'APP_ENV=' + environment.get()
    }
}
```

Use only **one** DSL per build file in a given test; do not paste both snippets simultaneously.

## 7. Separating the Gradle Build JVM from the Spring Boot Runtime JVM

Typical process hierarchy:

```text
Shell / CI
   |
   +-- Gradle wrapper/client -> Gradle daemon (JVM running build logic)
                                    |
                                    +-- compileJava / test (may use worker/test JVM)
                                    |
                                    +-- bootRun -> Spring Boot application JVM
                                    |
                                    +-- bootJar -> executable JAR file (app not running yet)
                                                     |
                                                     +-- java -jar app.jar (separate JVM, at runtime)
```

`./gradlew bootRun` executes the `BootRun` task (a `JavaExec` subclass) and starts the application in a separate JVM. `-P`, Gradle daemon system properties, and `org.gradle.jvmargs` **do not automatically become** application configuration. By contrast, regular OS environment variables are normally inherited by child processes unless customized by the task/CI.

There are three clear ways to pass configuration **into a Spring Boot application** when using `bootRun`:

1. Pass application args via `bootRun --args='--spring.profiles.active=dev --server.port=9090'`.
2. Provide runtime environment variables recognized by Spring Boot, such as `SPRING_PROFILES_ACTIVE=dev` or `SERVER_PORT=9090`.
3. Configure `tasks.named<BootRun>("bootRun") { systemProperty(...); environment(...) }` to map Gradle values into the app JVM when genuinely needed.

When packaging into a JAR, **options 1 and 2 belong to running the JAR**, not to when `bootJar` creates the artifact. `-Penv=prod` has no default Spring Boot meaning when running `bootJar` alone.

## 8. Runnable Spring Boot Example: Passing Configuration from Gradle to the App

This example uses **Spring Boot 3.5.0**, Java **17+**, pinning versions as a reference point for code and commands; this is **not** a claim of the latest version. Network access is needed for Gradle to download plugins/dependencies. If your project has a Gradle Wrapper, use the repo's wrapper; the example below can use a compatible installed Gradle if you have not generated a wrapper yet.

Structure:

```text
spring-property-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/main/java/com/example/propertydemo/PropertyDemoApplication.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "spring-property-demo"
```

**`build.gradle.kts`:**

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}

tasks.named<BootRun>("bootRun") {
    // Forward only when -PdemoMessage or an equivalent project property source is present.
    providers.gradleProperty("demoMessage").orNull?.let { value ->
        systemProperty("demo.message", value)
    }
}
```

**`src/main/java/com/example/propertydemo/PropertyDemoApplication.java`:**

```java
package com.example.propertydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PropertyDemoApplication {
    private final String message;

    public PropertyDemoApplication(
            @Value("${demo.message:from-default}") String message) {
        this.message = message;
    }

    @GetMapping("/message")
    public String message() {
        return message;
    }

    public static void main(String[] args) {
        SpringApplication.run(PropertyDemoApplication.class, args);
    }
}
```

In Java, `@Value("${demo.message:from-default}")` uses a **Spring property placeholder**. If `demo.message` is not provided from any source, the app returns `from-default`. If provided, Spring `Environment` resolves the value according to runtime precedence.

### 8.1. Using `--args`: Passing Application Arguments Directly

```bash
./gradlew bootRun --args='--demo.message=from-args'
```

Open another terminal:

```bash
curl -fsS http://localhost:8080/message
```

**Exact response body:** `from-args` (not necessarily with a trailing newline). The `curl` command assumes the server started successfully on port 8080 and the port is not occupied by another application. Stop the server with Ctrl+C.

Switching to `--args='--server.port=9090 --demo.message=from-args'` moves the endpoint to `http://localhost:9090/message`. This is the direct way to pass arguments to Spring Boot without `-P` or `-D`.

### 8.2. Using `-P` and Forwarding to the Application JVM

```bash
./gradlew bootRun -PdemoMessage=from-project
```

Because `build.gradle.kts` includes `providers.gradleProperty("demoMessage").orNull?.let { systemProperty(...) }`, Gradle reads the project property and **configures the `bootRun` task** to set Java system property `demo.message=from-project` on the application JVM.

Call:

```bash
curl -fsS http://localhost:8080/message
```

**Response body:** `from-project`.

If you **remove** the mapping block in `tasks.named<BootRun>`, passing `-PdemoMessage=from-project` **will not automatically change** the Spring Boot property `demo.message`. This is the single most common point of confusion when controlling Spring Boot via Gradle.

### 8.3. `-D` on Gradle Does Not Automatically Enter the Application JVM

```bash
./gradlew bootRun -Ddemo.message=from-gradle
```

Because the sample build script **does not** map `providers.systemProperty("demo.message")`, `from-gradle` stays inside the Gradle build JVM. With no other configuration source present, the endpoint still returns `from-default`.

If you genuinely want to map a Gradle `-D` into the Spring Boot JVM, add **inside the `tasks.named<BootRun>("bootRun")` block**:

```kotlin
providers.systemProperty("demo.message").orNull?.let { value ->
    systemProperty("demo.message", value)
}
```

This snippet is an **optional addition** to the existing block. Use it only for a concrete reason; usually `--args` or environment variables are clearer. If both the `demoMessage` project property and `demo.message` system property are set at once, explicitly define which source wins in build logic, since two `systemProperty` calls can overwrite each other depending on configuration order.

### 8.4. Using Spring Boot Environment Variables Directly

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun
```

When **not** passing `-PdemoMessage` and no other system property is forwarded for `demo.message`, the app JVM inherits `DEMO_MESSAGE`. Spring Boot supports relaxed binding for environment variable names so `DEMO_MESSAGE` maps to `demo.message`. The endpoint returns `from-env`.

You can use standard environment variables:

```bash
SPRING_PROFILES_ACTIVE=dev SERVER_PORT=9090 ./gradlew bootRun
```

The app runs on port 9090 with profile `dev` active, unless overridden by a higher-precedence source. Do not confuse this with `ORG_GRADLE_PROJECT_demoMessage=from-env`: that supplies a **project property** to Gradle; in the sample build script it reaches the app **only because of the explicit mapping we wrote**, not because Spring Boot understands `ORG_GRADLE_PROJECT_`.

### 8.5. After Building the Executable JAR: Runtime Uses Its Own Channels

Package:

```bash
./gradlew clean bootJar
```

With the example's project name/version, the artifact is usually `build/libs/spring-property-demo-0.1.0.jar`. Check the actual filename in `build/libs` if the build is customized.

Three ways to run:

```bash
# Spring Boot application arguments
java -jar build/libs/spring-property-demo-0.1.0.jar --demo.message=jar-args

# Java system property of the application JVM itself: -D MUST precede -jar
java -Ddemo.message=jar-jvm -jar build/libs/spring-property-demo-0.1.0.jar

# Environment variable of the Java process
DEMO_MESSAGE=jar-env java -jar build/libs/spring-property-demo-0.1.0.jar
```

Run each command separately, stopping the previous process before starting the next. `curl http://localhost:8080/message` returns `jar-args`, `jar-jvm`, or `jar-env` respectively when no higher-precedence source overrides it. In all three commands **Gradle is no longer running**; `-P` does not exist and `-D` on the `java` command is a system property of the application JVM itself.

## 9. Passing Configuration to `Test`, `JavaExec`, and Custom Tasks

Not only `bootRun`—other Gradle tasks that launch child JVMs also require distinguishing scopes:

- `Test` runs tests in one or more separate JVMs.
- `JavaExec`/`BootRun` launches a Java application in another process.
- Compiler daemons/workers have their own runtime mechanisms depending on plugins and Gradle version.

Example **addition for a project with the Java plugin applied** when passing a project property into the test JVM:

```kotlin
tasks.withType<Test>().configureEach {
    val testMode = providers.gradleProperty("testMode").orElse("local")
    systemProperty("demo.test.mode", testMode.get())
}
```

`./gradlew test -PtestMode=ci` causes the test JVM to see `System.getProperty("demo.test.mode")` as `ci` when tests run. This is task configuration; it **does not** mean `-Ddemo.test.mode=ci` on the Gradle CLI is automatically forwarded to the test JVM. In Groovy DSL:

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'demo.test.mode', providers.gradleProperty('testMode').orElse('local').get()
}
```

To inject a specific OS variable into `JavaExec` or `Test` JVMs (e.g., tests needing a sandbox endpoint), configure `environment("API_BASE_URL", value)` on the task; OS environment variables from the shell are normally inherited by child processes, yet explicit configuration controls names/values and makes tests easier to verify.

**Important:** for tests whose behavior depends on varying inputs, declare/forward inputs properly so the task is not marked `UP-TO-DATE` when results actually depend on an environment variable or untracked property. `Test`'s `systemProperty` API lets Gradle factor that value into test execution; for custom tasks, declare `@Input` or `inputs.property(...)` and matching outputs so up-to-date checks and the build cache remain accurate. Reading `System.getenv` directly inside `doLast` and writing a file without declaring inputs can cause the cache to return stale results.

## 10. Build Logic Should Use the Provider API and Handle Missing Values Intentionally

Three common APIs:

```kotlin
val branch = providers.gradleProperty("buildBranch")
val trace = providers.systemProperty("demo.trace")
val endpoint = providers.environmentVariable("SERVICE_ENDPOINT")
```

Each returns a `Provider<String>`. You can:

- `.orElse("local")`: provide a default if no source supplies a value.
- `.map { ... }`: transform the value lazily.
- `.isPresent` or `.orNull`: check presence before configuring an option.
- `.get()`: obtain the value; throws an error if absent with no default.
- `.orElse(otherProvider)`: build fallback chains across multiple sources.

Example of a project property selecting a build variant that must match an allowed set:

```kotlin
val buildFlavor = providers.gradleProperty("buildFlavor").orElse("local")
val acceptedFlavors = setOf("local", "qa", "prod")

tasks.register("validateFlavor") {
    doLast {
        val flavor = buildFlavor.get()
        require(flavor in acceptedFlavors) {
            "Unsupported buildFlavor: $flavor"
        }
        println("buildFlavor=" + flavor)
    }
}
```

Running `./gradlew -q validateFlavor -PbuildFlavor=qa` prints `buildFlavor=qa`. Any other value makes the task fail with a clear error. Do not assume this setup connects to a production deployment or runtime environment: this example only validates a custom task's input.

**Configuration cache:** using `Provider` lets Gradle track build configuration inputs. Avoid implicitly capturing `project`/`gradle`/`rootProject` inside task actions when writing custom tasks; use task properties and proper service APIs. When a property affects a custom task's output, declare it as a task input (e.g., `@Input Property<String>`) rather than merely reading it inside the action.

## 11. Organizing `gradle.properties` and CI/CD

### 11.1. Types of Configuration Files

**Project root `gradle.properties`** (safe to commit **non-sensitive** values):

```properties
org.gradle.caching=true
org.gradle.parallel=true
buildFlavor=local
```

**User-private `~/.gradle/gradle.properties`** (never commit):

```properties
# Sensitive values shown only to illustrate key names; DO NOT put into a Git repo
corpRepoUsername=service-account
corpRepoPassword=secret-injected-by-secure-process
```

When CI injects values, prefer your platform's secret mechanism instead of writing passwords to persistent files. Note that relying on a "user-level file" reduces reproducibility if teammates lack that file; document **required property names** and set safe defaults for non-sensitive settings.

### 11.2. CI Passing Project Properties via Environment Variables

Instead of exposing tokens on the command line:

```bash
./gradlew publish -PrepoPassword=real-secret
```

Let CI provide `ORG_GRADLE_PROJECT_repoPassword` from its secret store, while the build script reads `providers.gradleProperty("repoPassword")` or uses plugin-specific credentials mechanisms. Flow:

```text
CI secret store
   -> ORG_GRADLE_PROJECT_repoPassword (environment of Gradle process)
   -> providers.gradleProperty("repoPassword")
   -> repository/publishing task config
```

In Gradle, a repository named `corpRepo` also supports the convention for `PasswordCredentials` using `corpRepoUsername` and `corpRepoPassword` properties. Kotlin DSL **configuration snippet inside `build.gradle.kts`**:

```kotlin
repositories {
    maven {
        name = "corpRepo"
        url = uri("https://repo.example.org/repository/maven-private/")
        credentials(PasswordCredentials::class)
    }
}
```

When the repository requires authentication, Gradle can automatically obtain credentials from properties following that convention; CI supplies `ORG_GRADLE_PROJECT_corpRepoUsername` and `ORG_GRADLE_PROJECT_corpRepoPassword`. The URL `example.org` is illustrative, not a live endpoint. Do not force credentials onto public Maven Central.

**Practical security:** environment variables are not a vault; processes with sufficient permissions or job/log dumps can still expose values. Never echo secrets, never put tokens into artifact names or publicly displayed commands, and never dump all Gradle properties into build scans or test output. If a token is ever committed or printed in logs, rotate it. Avoid passing Spring Boot runtime secrets merely to build a JAR if the build does not need them.

### 11.3. Which Mechanism Should You Choose?

| Scenario | Recommended mechanism | Reason |
| --- | --- | --- |
| Toggling a custom task flag at build time | `-PbuildFlavor=qa` | Build logic reads it directly and transparently |
| CI supplying repository credentials | `ORG_GRADLE_PROJECT_...` from secret store | Keeps secrets off the CLI and out of Git |
| Configuring Java proxy for Gradle | `-Dhttps.proxyHost=...` or `systemProp.https.proxyHost` | Proxies are Gradle/JVM networking system properties |
| Selecting a Spring profile for `bootRun` | `--args='--spring.profiles.active=dev'` or `SPRING_PROFILES_ACTIVE` | Sent directly to the runtime application |
| Changing port when running the JAR | `java -jar app.jar --server.port=9090` or `SERVER_PORT` | Decouples deployment runtime from the build |
| Running tests needing a test property | `-PtestMode=ci` + `Test.systemProperty(...)` | Explicitly forwards into the forked test JVM |
| Configuring Gradle daemon heap | `org.gradle.jvmargs` | Distinct from the application JVM heap |
| Configuring standalone app heap | `java -Xmx... -jar app.jar` | Targets the actual application JVM |
| Production app configuration | Deployment config/secrets (env, config file, secret store) | Never bake secrets into packaged artifacts |

## 12. Common Errors and How to Diagnose Them

| Symptom | Common cause | Check / fix |
| --- | --- | --- |
| `-Pfoo=x` passed, yet Spring Boot still gets default | Project property was not forwarded to Spring Boot JVM | Use `bootRun --args` / env or add `BootRun.systemProperty` mapping |
| `-Dfoo=x` passed, yet `providers.gradleProperty("foo")` is empty | `-Dfoo` is a system property, not a project property | Use `providers.systemProperty("foo")` or `-Dorg.gradle.project.foo=x` |
| `ORG_GRADLE_PROJECT_foo` has no effect | Wrong case/name, variable missing from Gradle env, overridden by `-P` | Check spelling and precedence using a task that prints **non-sensitive** values |
| `gradle.properties` has `foo=local`, yet CLI sees `ci` | `-P` / system prefix / env override or user-level file has another value | Check sources for that key and Gradle user home file |
| Ran `-Dserver.port=9090` with `gradlew bootRun`, server still listens on 8080 | `-D` was set on the Gradle JVM, not the app JVM | Use `bootRun --args='--server.port=9090'` |
| `bootRun -PdemoMessage=...` works, yet executable JAR ignores it | `-P` mapping lives in `BootRun` task and does not exist for standalone JAR runs | Supply runtime config via `java -D... -jar`, `--...`, or env |
| `java -jar app.jar -Ddemo.message=x` does not change property | `-D` placed after JAR name is treated as an application arg | Put JVM options before `-jar`: `java -Ddemo.message=x -jar app.jar` |
| Test JVM does not see Gradle's `-Dfoo=x` | `Test` task forks a separate JVM | Configure `Test.systemProperty("foo", ...)` |
| CI sees empty property while dev sees right value | CI does not inject env/user-level file or variable name differs | Compare **non-sensitive** environment, root/user Gradle properties, and job config |
| Build cache enabled, yet outputs go stale when env changes | Custom task did not declare env/property as an input | Use `Provider` with `@Input` or `inputs.property` |
| Settings in subproject `gradle.properties` have no effect | `providers.gradleProperty` does not arbitrarily scan all subproject files; `systemProp` only works at root/user | Put build-level properties in root or user home |
| Spring Boot env `SERVER_PORT` overridden by CLI args | Runtime config sources have their own precedence | Check `--server.port`, Java system properties, and active config files |
| Secret printed in build logs | Task/debug script called `println` or Gradle CLI contained token | Remove logs, rotate token, use secret manager/CI masking and least privilege |

### Short Debugging Workflow

1. Identify **where the value must arrive**: Gradle script, Gradle JVM, forked `Test`/`bootRun`, or post-deployment JAR JVM.
2. Record the exact command invoked, e.g., `./gradlew bootRun -Pprofile=dev` vs. `./gradlew bootRun --args='--spring.profiles.active=dev'`.
3. Match the exact source API: `gradleProperty`, `systemProperty`, `environmentVariable`, or Spring `Environment`.
4. For a Spring Boot application, inspect the **forwarding path**: `--args`, `BootRun.systemProperty`, `BootRun.environment`, or inherited environment variables.
5. Check precedence for that key and active configs; if a user-level `gradle.properties` exists, compare it against project root.
6. In CI/production, log only property names and presence status or **non-sensitive** values; never dump secrets to terminals.
7. Re-run in a realistic environment and verify actual outcomes: HTTP endpoint, test assertion, or artifact output. Do not guess solely from Gradle exiting cleanly.

## 13. Short Practice Exercises

With the `showInputs` task from section 6, predict the output before running:

**Exercise A.** Project root has `gradle.properties`:

```properties
buildMode=local
```

Run `APP_ENV=qa ./gradlew -q showInputs -PbuildMode=ci -Ddemo.trace=on`. Result:

```text
buildMode=ci
demo.trace=on
APP_ENV=qa
```

`-P` overrides `gradle.properties`; `-Ddemo.trace` is the Gradle JVM system property; `APP_ENV` is an environment variable.

**Exercise B.** Without `-P`, set `ORG_GRADLE_PROJECT_buildMode=integration` and run `./gradlew -q showInputs -DbuildMode=system-only`. Assuming no other overrides:

```text
buildMode=integration
demo.trace=disabled
APP_ENV=unset
```

`-DbuildMode=system-only` does not override the project property because it lacks the `org.gradle.project.` prefix.

**Exercise C.** In section 8's Spring Boot project, run `./gradlew bootRun -PdemoMessage=from-P --args='--demo.message=from-args'`. With two sources setting `demo.message`, the app returns **`from-args`**, because Spring Boot command-line args have higher precedence than the Java system property forwarded by `BootRun`. This is a **Spring Boot runtime precedence rule**, not Gradle's precedence between `-P` and `-D`.

**Exercise D.** Run the executable JAR with `DEMO_MESSAGE=from-env java -Ddemo.message=from-jvm -jar build/libs/spring-property-demo-0.1.0.jar`. The endpoint returns **`from-jvm`** because the Java system property on the **application's own JVM** takes precedence over the environment variable for that key.

## 14. Official Documentation for Reference

- Gradle – [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): project/system/Gradle properties, environment variables, configuration channels, and precedence.
- Gradle – [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `-P`, `-D`, and Gradle options.
- Gradle – [Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider` and property APIs.
- Gradle – [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tracking build configuration inputs.
- Gradle – [Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task inputs/outputs and state declarations.
- Spring Boot Gradle Plugin – [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun`, `--args`, `systemProperty`.
- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): environment variables, Java system properties, command-line args, and `PropertySources`.

**Rule to remember:** `-P` sets a **project property for Gradle**, `-D` sets a **system property for the JVM running Gradle** (with the special exception `-Dorg.gradle.project.*` creating a project property), and environment variables are **OS process data** (the `ORG_GRADLE_PROJECT_*` prefix is converted by Gradle into a project property). `bootRun`, `Test`, and `java -jar` each have their own JVM/runtime; choose the appropriate forwarding mechanism and check precedence **where the value is consumed**.