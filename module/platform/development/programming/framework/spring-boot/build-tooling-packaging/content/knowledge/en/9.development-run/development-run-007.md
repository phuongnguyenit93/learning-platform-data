# Including DevTools in Development with the Proper Dependency Scope

During Spring Boot development, we often want to see code changes quickly without shutting down the application, performing a full restart, and manually retesting after every compile. **Spring Boot DevTools** (`org.springframework.boot:spring-boot-devtools`) supports that development loop through automatic restarts, LiveReload, and developer-friendly configuration defaults. However, these mechanisms belong to **development** and should not ship in a production deliverable.

The central question of this lesson: **How do you put DevTools on the classpath during development while keeping it out of downstream consumers or deployable executable artifacts?** The answer depends on two distinct mechanisms in Maven and Gradle:

- **Maven:** declare DevTools as an **optional dependency**; you may add `<scope>runtime</scope>` to make clear that application source code does not need the DevTools API at compile time. The Spring Boot Maven Plugin excludes DevTools from the executable archive in its default configuration.
- **Gradle:** place DevTools in the **`developmentOnly`** configuration provided by the Spring Boot Gradle Plugin. It is available for development workflows and is omitted from `bootJar`/`bootWar` by default.
- **Always inspect the packaged artifact**, because plugin, scope, publication, or custom task changes can alter default behavior.

Examples use **Java 17 + Spring Boot 3.3.13** and two separate build choices: Maven 3.9.x or a Gradle version compatible with Spring Boot 3.3. Fixed versions help learners reproduce the examples; real projects must choose versions consistent with their support lifecycle and update policies.

## 1. What Is DevTools For?

`spring-boot-devtools` is a development helper module, not a business-logic Spring Boot starter. Key features include:

| Feature | Meaning | Limitations to Understand |
| --- | --- | --- |
| Automatic restart | When classpath contents (typically `.class` files) change, the app reloads the application context faster | **Not** an instant hot swap of all bytecode as you type source; classpath output must be updated via compile/build |
| Two classloaders | Keeps relatively stable libraries in a *base classloader* and recreates a *restart classloader* for active development code | Can cause classloading issues with specialized modules or libraries |
| Development property defaults | Adjusts cache/template/resource defaults to make UI edits convenient | Never treat these values as production-appropriate defaults |
| LiveReload | Signals LiveReload-capable browsers/clients to refresh automatically | Does not replace frontend build tooling and may require client/browser extension support |
| Condition evaluation delta report | Shows auto-configuration changes after a restart | Useful for diagnostics, not a substitute for full testing |

When a fully packaged application runs via `java -jar`, Spring Boot treats it as a production environment by default and automatically disables DevTools via launcher detection; furthermore, **standard packaging plugins exclude DevTools from the executable archive by default**. These two layers of protection serve distinct purposes:

1. **Classpath/artifact:** Is DevTools included in the release deliverable at all?
2. **Runtime activation:** Even if the DevTools JAR were present, are development features enabled when the application runs?

Never use the second layer as an excuse to skip verifying the first. The best production artifact **does not contain DevTools**.

## 2. "Dependency Scope" vs. "Feature Enablement"

When declaring a dependency, the build tool must know which stage needs it:

```text
                      JAVA PROJECT
                           |
            +--------------+--------------+
            |                             |
       IDE Build/Run               Release Artifact
            |                             |
   DevTools on classpath?        JAR/WAR has DevTools?
            |                             |
      YES, during dev                    NO
            |                             |
   Restart/LiveReload            Production environment
```

**Maven `optional` and Gradle `developmentOnly` are not implementation synonyms.**

- `optional` in Maven controls **transitivity** when your module is consumed by another project. A direct optional dependency can still appear on the classpath of the **declaring project itself**.
- `developmentOnly` in Gradle is a **configuration** supported by the Spring Boot Gradle Plugin for development-only dependencies. It is not included in the executable archive under default packaging configuration.
- Maven's `runtime` scope and Gradle's `runtimeOnly` configuration describe runtime dependencies, but **by themselves they do not ensure a dependency is excluded from the production artifact**.
- Maven's `test` scope and Gradle's `testImplementation` restrict dependencies to tests; declaring DevTools only there means running via `spring-boot:run`/`bootRun` in the main development workflow will not necessarily include DevTools.
- `provided`/`compileOnly` are inappropriate as default mechanisms for DevTools: they imply compile-only or container-provided libraries, contradicting the goal of having DevTools present when running the app **during development**.

### Quick Selection Table

| Goal | Maven | Gradle |
| --- | --- | --- |
| Use DevTools when running from IDE/build tool | Direct `spring-boot-devtools` dependency with `optional=true` (optionally `scope=runtime`) | `developmentOnly 'org.springframework.boot:spring-boot-devtools'` |
| Avoid propagating DevTools to downstream modules | `<optional>true</optional>` | Use `developmentOnly` instead of `api`/`implementation` |
| Keep DevTools out of executable archive | Spring Boot Maven Plugin: default `excludeDevtools=true` | Spring Boot `bootJar`/`bootWar`: excludes `developmentOnly` by default |
| Library used solely in tests | `<scope>test</scope>`, not the primary choice here | `testImplementation`, not the primary choice here |
| Verify actual outcome | `mvn dependency:tree` + `jar tf target/...jar` | `./gradlew dependencies` + `jar tf build/libs/...jar` |

## 3. Maven: Declaring DevTools So Your Project Uses It Without Downstream Inheritance

### 3.1. Core Configuration Snippet

In the `pom.xml` of a Spring Boot app with dependency version management (e.g., inheriting `spring-boot-starter-parent`), add this **dependency** inside `<dependencies>`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
```

**Meaning of each element:**

- `groupId`/`artifactId`: selects the Spring Boot DevTools module.
- Omit `<version>`: the starter parent or `spring-boot-dependencies` BOM provides the managed version matching the Spring Boot release. If your project lacks dependency management, specify the matching version explicitly.
- `<scope>runtime</scope>`: the compiler does not need DevTools APIs when compiling main sources; the dependency remains available on the application's runtime classpath during development runs. **Spring Boot 3.3 documentation also shows DevTools with only `optional=true` and Maven's default `compile` scope; both approaches can work.** Using `runtime` makes this lesson's intent explicit.
- `<optional>true</optional>`: downstream projects depending on this project will **not automatically** receive DevTools transitively. It does not remove the dependency from this project's own classpath.
- Spring Boot Maven Plugin's `repackage` goal excludes `spring-boot-devtools` from executable JAR/WAR files by default via `excludeDevtools=true`. That is **packaging plugin** behavior, not a general property of the `optional` tag.

### 3.2. Standalone Maven `pom.xml` Example

A minimal POM for a Java 17 web application:

```xml
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

    <groupId>dev.example</groupId>
    <artifactId>devtools-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
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

`spring-boot-starter-parent` supplies both dependency management and Maven Plugin configuration, so declaring `spring-boot-maven-plugin` above binds `repackage` into the `package` lifecycle phase. If using a corporate parent that **only imports the BOM** instead of inheriting the starter parent, declare the Spring Boot Maven Plugin version and `repackage` execution explicitly per your build setup; a BOM import alone **does not** trigger `repackage`.

The output `target/devtools-demo-1.0.0.jar` will be an executable JAR if build and `repackage` succeed. DevTools may still appear in the dependency graph **for development runs**, while being excluded from the executable JAR under default Boot 3.3 settings.

### 3.3. Shared Java Code and Tests

Use one project source tree for Maven **or** Gradle with this layout:

```text
devtools-demo/
├── pom.xml                 # Choose Maven
├── src/
│   ├── main/java/dev/example/devtools/
│   │   └── DevtoolsDemoApplication.java
│   └── test/java/dev/example/devtools/
│       └── DevtoolsDemoApplicationTests.java
└── (or settings.gradle + build.gradle if choosing Gradle)
```

File `src/main/java/dev/example/devtools/DevtoolsDemoApplication.java`:

```java
package dev.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DevtoolsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevtoolsDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello v1";
    }
}
```

File `src/test/java/dev/example/devtools/DevtoolsDemoApplicationTests.java`:

```java
package dev.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DevtoolsDemoApplicationTests {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloResponds() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello v1"));
    }
}
```

This example uses only Spring MVC and JUnit, **without importing any DevTools class in source code**. That aligns with Maven `runtime` or Gradle `developmentOnly`: DevTools is a development tool, and business code has no reason to depend on its API.

### 3.4. Running with Maven

Requires JDK 17 and a compatible Maven. If the project includes a Maven Wrapper, replace `mvn` with `./mvnw` (Windows: `mvnw.cmd`).

```bash
mvn -version
mvn clean verify
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools
mvn spring-boot:run
```

- `mvn clean verify` verifies compilation/tests and produces the JAR during `package`; Maven does not keep the application running long-term just because the build succeeded.
- `mvn dependency:tree` lists DevTools as resolved in this project's own dependency graph. With the configuration above, the direct entry shows `runtime` scope and the optional flag.
- `mvn spring-boot:run` starts the application for development from the classpath; DevTools can operate once the dependency is resolved. Do not replace `spring-boot:run` with `java -jar` when testing restarts.
- If the IDE runs `main` directly with the module's runtime classpath, DevTools can also activate via Spring Boot's development detection.

In a second terminal once the application is ready:

```bash
curl -s http://localhost:8080/hello
```

Exact HTTP body:

```text
Hello v1
```

## 4. Gradle: Putting DevTools in `developmentOnly`

### 4.1. Recommended Configuration Snippet

With the **Spring Boot Gradle Plugin**, usually all you need is:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

`developmentOnly` is a configuration created by the Boot plugin. When running from source via `bootRun`, DevTools can participate in the development runtime classpath. When `bootJar`/`bootWar` builds the executable archive by default, dependencies in `developmentOnly` **are excluded from the artifact**.

Never declare DevTools under `implementation` assuming it will vanish simply because its artifact name contains "devtools." Controlling the classpath with `developmentOnly` expresses project intent directly in configuration and aligns with the Spring Boot plugin's packaging rules.

### 4.2. Complete `build.gradle` (Groovy DSL)

File `settings.gradle`:

```groovy
rootProject.name = 'devtools-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this setup, the Spring Boot Gradle Plugin works with `io.spring.dependency-management` to import the corresponding Spring Boot BOM, so `spring-boot-devtools` needs no explicit version. If a project replaces that with Gradle native `platform(...)`, ensure the **configuration holding DevTools** receives appropriate version constraints; adding `platform` only to `implementation` without checking other configurations can leave versions unmanaged.

Use the same two Java source files from Section 3.3. Build with the Gradle Wrapper if provided by the project:

```bash
./gradlew clean build
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
./gradlew bootRun
```

Windows uses `gradlew.bat`. The `bootRun` task uses the main runtime classpath to launch the app from build outputs. In a project with the Spring Boot plugin, `runtimeClasspath` includes development dependencies suitable for local development, while `bootJar` uses a packaging classpath tailored to omit `developmentOnly` dependencies.

`dependencyInsight` helps trace why a dependency was chosen and its actual resolved version. In projects with customized source sets or configurations, inspect the dependency graph of the exact task/configuration rather than extrapolating from a single configuration name.

### 4.3. Why Not Use `runtimeOnly` in Gradle?

`runtimeOnly` means **the dependency is needed to run the application**, without signaling "only during development" to packaging tasks. The Spring Boot plugin created `developmentOnly` precisely to express that distinction. With `runtimeOnly 'org.springframework.boot:spring-boot-devtools'`, depending on task config and plugin version, the library can end up on the runtime classpath consumed by `bootJar`; never rely on it as a safe default development scope.

Also avoid `testImplementation` if you want DevTools when running the app via `bootRun`: the test configuration serves compiling/running tests and does not automatically put dependencies on the main development runtime.

**Use `developmentOnly` with Gradle** and verify by inspecting the artifact.

## 5. Practicing DevTools Restart and Observing the Right Signals

DevTools does not watch every keystroke inside `.java` files like an embedded compiler inside the JVM. It watches for changes in **classpath directory entries** and triggers a restart when compiled output changes.

Workflow:

1. Start `mvn spring-boot:run`, `./gradlew bootRun`, or the application `main` from an IDE with DevTools on the runtime classpath.
2. From another terminal, call `curl -s http://localhost:8080/hello` and receive `Hello v1`.
3. Change **only** the return string in `DevtoolsDemoApplication.hello()` to `"Hello v2"`.
4. Let the IDE compile the project, or run `mvn compile` / the corresponding Gradle compile task to update `.class` files.
5. Watch the app restart when the classpath changes and call the endpoint again; once restarted, the body is `Hello v2`.
6. To re-run `mvn clean verify`/`./gradlew clean build` after editing the code, **also update the expected string in the test to `Hello v2`** or revert the source back to `Hello v1`. Otherwise, the test will rightly fail.

Observation flow:

```text
Source /hello -> "Hello v1"
        |
        v
Build/IDE compile -> classpath contains .class v1
        |
        v
DevTools running in development JVM
        |
        +--- edit source to "Hello v2"
        |
        +--- compiler updates .class v2
        |
        v
DevTools detects classpath change -> restarts context
        |
        v
HTTP /hello -> "Hello v2"
```

**Restart vs. static reload:** editing static HTML/CSS/JS assets may only trigger a browser reload without restarting the Java application context. DevTools defines default path exclusions that do not trigger a full restart; LiveReload is a separate helper that depends on a compatible client/browser.

**Not every source edit restarts immediately:** if your IDE does not auto-compile on save, the classpath still holds old `.class` files. Usually compilation simply hasn't happened or the output path isn't watched by DevTools—not that DevTools "failed to read `.java`."

### Temporarily Disabling Restart for Diagnostics

If you hit classloader issues in an internal module or specialized library, try the property:

```properties
spring.devtools.restart.enabled=false
```

This is a **development-time setting** to disable restarts. When you merely disable restart via a properties file, some DevTools components may still initialize; to remove it completely from the project/runtime classpath, remove the dependency in the build. For production, the right approach is building an artifact without DevTools rather than hiding the dependency behind a property.

Never force-enable DevTools restart inside a production environment. DevTools provides monitoring and modification capabilities intended for developer workflows; forcing it on in public environments creates operational and security risks.

## 6. Separating Three Concepts: Dev Dependency, Spring Profile, and Build Profile

A common conceptual mistake is thinking that setting the Spring profile `dev` **automatically pulls in** `spring-boot-devtools`, or that Maven `-Pdev` automatically selects a DevTools scope.

In reality, there are three independent controls:

| Control | Who Decides? | Examples | Purpose |
| --- | --- | --- | --- |
| Dependency/configuration | Maven or Gradle | `<optional>true</optional>`; `developmentOnly` | Controls whether the DevTools JAR is on the dev classpath and/or in the artifact |
| Spring runtime profile | Spring Boot | `--spring.profiles.active=dev`, `application-dev.yml` | Selects properties and beans at application startup |
| Maven build profile | Maven | `mvn -Pci clean verify` | Selects POM configuration/goals during the build |

If `spring-boot-devtools` is **not** on the classpath, passing `--spring.profiles.active=dev` alone will **not** add the module. Conversely, if the dependency is declared properly, you do not need to create a Spring profile named `dev` for DevTools to work in development.

In Spring Boot, `spring.profiles.active` has its own purpose for application configuration; do not treat it as a substitute for `developmentOnly` or Maven `optional`. Likewise, `<scope>runtime</scope>` does not set `spring.profiles.active`. They operate at different layers.

## 7. Verifying DevTools Is Truly Absent from the Executable JAR

**Never treat a passing `mvn clean verify` or `./gradlew clean build` as sufficient proof of dependency scoping.** A build can succeed even if someone changed dependency classification so a dev-only JAR gets bundled into the release artifact. Inspect the **actual JAR/WAR file intended for deployment**.

### Maven: Inspecting the `repackage`d JAR

After running:

```bash
mvn clean verify
```

Inspect contents:

```bash
jar tf target/devtools-demo-1.0.0.jar
```

A Spring Boot executable JAR typically contains:

```text
BOOT-INF/classes/dev/example/devtools/DevtoolsDemoApplication.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
...
```

Other entries, dependency versions, and listing order do not have to match this example. There **must not** be any entry starting with `BOOT-INF/lib/spring-boot-devtools-` in the default release build. If `repackage` was disabled or you inspected the un-repackaged/original JAR by mistake, the layout differs; verify the exact artifact your deployment pipeline uses.

Automated check on Linux/macOS:

```bash
if jar tf target/devtools-demo-1.0.0.jar | grep -q 'BOOT-INF/lib/spring-boot-devtools-'; then
  echo "FAIL: DevTools found in executable JAR"
  exit 1
else
  echo "PASS: DevTools absent from executable JAR"
fi
```

With the standard POM from Section 3, the check output **when passing** is:

```text
PASS: DevTools absent from executable JAR
```

PowerShell:

```powershell
$archive = "target/devtools-demo-1.0.0.jar"
$hits = jar tf $archive | Select-String 'BOOT-INF/lib/spring-boot-devtools-'
if ($hits) {
    throw "FAIL: DevTools found in executable JAR"
}
Write-Output "PASS: DevTools absent from executable JAR"
```

### Gradle: Inspecting `bootJar`

```bash
./gradlew clean build
jar tf build/libs/devtools-demo-1.0.0.jar
```

In the executable JAR, `BOOT-INF/lib/spring-boot-devtools-*.jar` must also be absent. In Gradle, if the project also produces `-plain.jar`, **do not confuse `-plain.jar` with the executable Boot JAR**. Pick the `bootJar` output matching the real name and version in `build.gradle`.

You can run the same shell check with the adjusted path:

```bash
if jar tf build/libs/devtools-demo-1.0.0.jar | grep -q 'BOOT-INF/lib/spring-boot-devtools-'; then
  echo "FAIL: DevTools found in executable JAR"
  exit 1
else
  echo "PASS: DevTools absent from executable JAR"
fi
```

**Your conclusion must rest on two observations:** DevTools is present during local runs (resolved in dependencies and restart loop works), and **absent** from the executable archive (`jar tf` checked against the exact artifact). Checking only one side does not prove the other.

## 8. Why Does Maven `optional` Not Mean "Development-Only"?

Maven's optional mechanism primarily applies when **another project consumes your artifact**. For example:

```text
Module app-a:
  depends on spring-boot-devtools (optional = true)
                     |
                     v
Module app-b:
  depends on app-a
  -> DOES NOT automatically receive spring-boot-devtools via app-a
```

For **`app-a` itself**, a direct optional dependency is still resolved by Maven and can appear on its runtime classpath. Therefore, claiming "setting `optional=true` prevents Maven from downloading DevTools when running this project" is wrong. The `optional` element governs transitivity; the Spring Boot Maven Plugin is what excludes DevTools during `repackage` of the executable archive.

Separate the following Maven options:

| Maven Configuration | Compile Classpath | Direct Project's Runtime Classpath | Transitive to Consumers |
| --- | --- | --- | --- |
| `<scope>compile</scope>` (default), non-optional | Yes | Yes | Yes, per mediation |
| `<scope>runtime</scope>`, non-optional | Not needed when compiling main sources | Yes | Yes, per runtime rules |
| `<scope>runtime</scope><optional>true</optional>` | Not needed when compiling main sources | Yes | **Not propagated automatically** |
| `<scope>test</scope>` | Not on main compile classpath | For tests | No |
| `<scope>provided</scope>` | Yes | Not treated as a normal self-contained app runtime dependency | Not like a regular compile dependency |

This table summarizes scopes at a conceptual level and omits nuances of plugins, test classpaths, dependency mediation, and container environments. For DevTools, **`runtime + optional` or Boot-documented `optional`** are both valid in Maven; verify with `dependency:tree` and the built artifact.

### Why Doesn't `test` Replace `runtime`?

DevTools assists developers while **running the application**, not as a JUnit assertion library. `test` puts a dependency into the test phase (and test classpaths), whereas `spring-boot:run` typically uses the main runtime classpath. Putting DevTools in `test` solely because "it shouldn't run in production" can strip you of DevTools when running the app locally.

### Why Avoid Maven `provided`?

`provided` is mainly for APIs or libraries supplied by the JDK or container that are needed during compile/test. With an executable Spring Boot JAR, using `provided` as a "trick" to drop a dependency can backfire because the Spring Boot Maven Plugin follows special rules for provided dependencies during `repackage`. Do not use `provided` as a substitute for `optional` to exclude DevTools.

## 9. Gradle: Understanding `developmentOnly` in the Larger Picture

Gradle organizes dependencies into configurations, and final classpaths are shaped by source sets, tasks, and `extendsFrom` relationships. The Spring Boot Gradle Plugin creates `developmentOnly` when applied alongside the Java plugin and configures run and packaging tasks according to its conventions.

In a standard build:

```text
implementation ------> main application compile/runtime
runtimeOnly  --------> main runtime; included in packaging
developmentOnly -----> local run workflow; excluded from bootJar/bootWar
testImplementation --> test compilation/runtime
testRuntimeOnly -----> test runtime
```

Common mistakes:

- Putting DevTools in the Java Library plugin's `api`: exposes it in API/dependency metadata to consumers, defeating dev-only intent.
- Putting DevTools in `implementation`: puts it on the application runtime classpath and can bundle it into archives depending on packaging.
- Putting DevTools in `testImplementation`: available in tests, yet `bootRun` will not receive it on the main runtime classpath.
- Using manual fat-jar/copy tasks instead of `bootJar`: the Boot plugin's default `developmentOnly` exclusion is **not automatically guaranteed** for custom packaging tasks.
- Customizing `tasks.named('bootJar') { classpath ... }` and accidentally adding `developmentOnly`: custom configuration itself alters release scope.

**Avoid breaking standard defaults:** this guide's goal is keeping `developmentOnly` local and keeping DevTools out of release artifacts, so there is no need to alter `bootJar.classpath` or set `excludeDevtools=false`. If an unusual requirement genuinely needs remote DevTools, evaluate it separately; it is not appropriate for standard production apps.

## 10. How Does Spring Boot Packaging Guard Against DevTools?

In Boot 3.3:

- **Maven Spring Boot Plugin (`repackage`):** `excludeDevtools` defaults to `true`. For executable JAR/WAR files, the plugin omits the DevTools artifact during packaging. If you do not use `repackage` or the standard plugin, do not infer from Maven `optional` that DevTools is excluded from other archives.
- **Gradle Spring Boot Plugin (`bootJar`/`bootWar`):** dependencies in `developmentOnly` are excluded by default. If you build custom `jar`, `shadowJar`, `distribution`, or Docker builds that copy dependency folders manually, verify those tools' scopes independently.
- **Runtime:** DevTools checks its execution environment and normally disables itself when a fully packaged app starts like a production application. That is a *runtime* safeguard, not a claim that shipping DevTools inside the archive is harmless.

### Multi-Module Builds and Libraries vs. Executable Applications

If a repository has `common` (a library) and `web-app` (an application), DevTools should normally be a direct development dependency of the **running `web-app` module**. Do not install it in a shared library consumed by every module. If a library uses DevTools for its own standalone tests/dev runs, scope it properly with `optional`/`developmentOnly` on that library and inspect published metadata.

In Maven, `optional=true` matters whenever module A is consumed by module B. In Gradle, `developmentOnly` matters because Gradle configurations and publications have different semantics from `api`/`implementation`. This prevents side effects in modules that never intended to use DevTools.

For a Spring Boot application module deployed with `java -jar`, CI should distinguish its artifacts: executable `bootJar`, plain library `jar` (if produced), and `bootWar` (if any). Inspect the actual deployable artifact, not just any file sharing the project name.

## 11. What If DevTools Still Appears in the Artifact?

Inspect in this order:

1. **Identify the exact output:** which `target/...jar` or `build/libs/...jar` file will actually be uploaded or deployed? Check the filename, `-plain` classifier, and manifest.
2. **Maven:** is `spring-boot-maven-plugin` running `repackage`? Is `excludeDevtools` overridden to `false`? `mvn help:effective-pom` shows the effective plugin configuration.
3. **Gradle:** is DevTools in `developmentOnly` on the right module? Was the same artifact also added via `implementation`/`runtimeOnly`/a custom configuration? Does a custom `bootJar`/Shadow/Copy task bundle every JAR?
4. **Run a clean build** to clear stale outputs, then run `jar tf`.
5. **Dependency graph:** use `mvn dependency:tree` or `./gradlew dependencyInsight` to find what pulls DevTools in.
6. **CI:** add an archive check gate failing the build if `BOOT-INF/lib/spring-boot-devtools-` appears; for WARs, inspect both `WEB-INF/lib/` and `WEB-INF/lib-provided/` per the actual layout.
7. **If a build plugin genuinely lacks exclusion support** for a custom artifact, fix packaging/dependency config on that task or choose a supported build workflow; do not merely disable restarts with a Spring runtime property and ignore the archive.

Conversely, when DevTools **fails to run during development**:

- Verify whether IDE/`bootRun`/`spring-boot:run` uses a runtime classpath containing DevTools.
- Verify whether the app is actually running from unpackaged classpath directories; `java -jar` behaves differently from `bootRun`.
- Verify whether the compiler/IDE updated `.class` files rather than only saving `.java`.
- Check for `spring.devtools.restart.enabled=false` or overly broad restart exclusions.
- Check for special multi-module classloaders or JRebel/AspectJ toolchains; some tools interact differently with default restart.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `mvn spring-boot:run` lacks DevTools | Missing dependency, wrong module, wrong runtime classpath, or excluded by profile | Check POM, effective model, `dependency:tree`, and plugin run config |
| `./gradlew bootRun` lacks DevTools | Placed in `testImplementation`/`compileOnly` or wrong plugin/configuration | Move to `developmentOnly` in the right module; inspect `runtimeClasspath` |
| Saved Java file, app does not restart | IDE has not compiled updated `.class` files | Compile/build project; confirm classpath output actually changed |
| Duplicate class / missing bean after restart | Two classloaders / devtools restart across multi-module | Temporarily disable restart to isolate; consider `META-INF/spring-devtools.properties` per docs |
| Maven `optional=true` yet still appears in `dependency:tree` | `optional` blocks transitivity, not direct project resolution | Expected behavior; inspect the executable archive separately |
| Maven used `test` scope and restart doesn't work when running app | Test scope is not on main runtime | Use an optional dependency, optionally with `runtime` scope |
| Gradle used `runtimeOnly` and Boot JAR contains DevTools | `runtimeOnly` does not mean development-only | Switch to `developmentOnly` and verify `bootJar` |
| `java -jar` does not restart like `bootRun` | Packaged launch is treated as production and DevTools is normally excluded | Run from source during development; do not force DevTools on in production |
| Boot JAR still contains DevTools | Plugin exclusion altered or custom packaging used | Inspect build tasks and `jar tf`; exclude DevTools from release artifacts |
| LiveReload present, browser does not refresh | Browser/client lacks LiveReload support, or only Java class changed without UI refresh | Check client extension/refresh path; distinguish restart from reload |
| Production startup leaks dev settings | DevTools or debug flags embedded in artifact or environment config | Remove dependency and debug options from release pipeline |
| DevTools version mismatches Spring Boot | Manually pinned version mismatched BOM/plugin | Manage via Boot BOM/release; verify resolved versions |

**Never "fix" this by deleting the dependency after each build.** Configuring the right scope so the build tool produces both the dev classpath and clean release artifacts is the repeatable solution.

## 13. Analysis Scenarios

**Scenario A.** A developer adds:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>test</scope>
</dependency>
```

and asks why `mvn spring-boot:run` has no automatic restart. **Answer:** DevTools was placed in test scope and is not guaranteed to be on the main runtime classpath. Change it to an `optional=true` dependency (optionally `scope=runtime`) as shown in Section 3.

**Scenario B.** A Maven app is imported by another project as a dependency; despite having DevTools, the consuming project does not inherit DevTools. **Answer:** That is the purpose of `optional=true`. It blocks transitive propagation without removing DevTools from the declaring app itself.

**Scenario C.** Gradle declares:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

assuming that `runtimeOnly` keeps DevTools out of production. **Answer:** Semantically incorrect; `runtimeOnly` is not dev-only. Switch to `developmentOnly` and inspect the archive.

**Scenario D.** A team runs `java -jar target/devtools-demo-1.0.0.jar` and sees no restart on source edits. **Answer:** That is a packaged executable artifact with DevTools excluded by default; the app runs in production mode. For development, use `mvn spring-boot:run`, `./gradlew bootRun`, or an IDE with the development classpath.

**Scenario E.** `pom.xml` marks DevTools optional, yet a custom script uploads all `target/dependency/*.jar` files to the server. Can we conclude the deployed environment lacks DevTools? **Answer:** No. The `optional` tag does not govern custom copies. You must inspect the copy command and deployed artifacts; `repackage` rules apply only to that plugin's output.

**Scenario F.** After editing Java source, the endpoint keeps returning `Hello v1` until choosing Build Project in the IDE. **Answer:** DevTools watches the compiled classpath; previously `.class` had not changed. Compiling creates the updated `.class`, giving DevTools the restart signal.

**Scenario G.** A Spring Boot app uses the `dev` profile without the DevTools JAR in its dependency graph. Does adding `spring.profiles.active=dev` install the module automatically? **Answer:** No. Spring profiles manage runtime config and beans, not Maven/Gradle dependencies.

**Scenario H.** `mvn clean verify` succeeds, and the artifact contains `BOOT-INF/lib/spring-boot-devtools-...jar`. Should the gate pass because tests passed? **Answer:** No. Investigate why default exclusion failed; fix the build/packaging setup, rebuild the artifact, and re-run the JAR dependency inspection.

## 14. Checklist for Production Projects

- **Right module:** declare DevTools on the Spring Boot application module launched during development, not accidentally in a shared library.
- **Right declaration:** Maven `optional=true` (consider `scope=runtime`); Gradle `developmentOnly`.
- **Right version:** use the Spring Boot BOM or matching dependency management to avoid DevTools version drift.
- **Right classpath:** launch the app from IDE/`spring-boot:run`/`bootRun` and verify DevTools works after compiling edits.
- **Right environment separation:** the `dev` Spring profile only controls configuration; it does not replace dependency scope.
- **Right artifact:** production executable JAR/WAR omits DevTools; verify via `jar tf` or archive inspection in CI.
- **Right plugin:** when using custom packaging, verify behavior explicitly because Boot plugin defaults do not cover arbitrary custom tasks.
- **Right release:** publish and deploy the exact verified artifact rather than rebuilding with another script that might pull in dev dependencies.
- **Right security:** never force remote DevTools/restarts on in production; manage secrets and debug endpoints per environment.
- **Right reproducibility:** version-control the Wrapper and build configuration with clean passing builds; keep test/inspection evidence for scope changes.

**Key takeaway:** `spring-boot-devtools` should be **present during development and absent from releases**. Maven uses **`optional`** to block transitive propagation, often paired with `runtime` scope to express intent; the Spring Boot Maven Plugin handles exclusion during `repackage`. Gradle uses **`developmentOnly`** to separate the development classpath from executable packaging. Always inspect both the dependency graph and **actual archive contents** before concluding.

### Official Documentation

- Spring Boot 3.3 — Developer Tools: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin: Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Running Your Application with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Apache Maven — Optional Dependencies and Exclusions: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Apache Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html