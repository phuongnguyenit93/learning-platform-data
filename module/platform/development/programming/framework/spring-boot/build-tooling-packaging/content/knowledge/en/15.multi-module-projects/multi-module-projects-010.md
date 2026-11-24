# Building a Single Module Separately and Verifying Product Independence

A multi-module Spring Boot repository is typically organized to reuse Java code, split responsibilities, and shorten feedback loops. However, the statement **"building module A separately succeeded"** is easily misinterpreted as **"A's product is completely independent"**. Those two conclusions are **not equivalent**.

Take an application `catalog-app` that uses an internal library `catalog-core`:

- You can ask Maven/Gradle to build only `catalog-app`, yet the build tool still has to locate or compile `catalog-core` if the application depends on it.
- You can run `catalog-app`'s executable Spring Boot JAR in a separate directory lacking `catalog-core`'s sources, because the JAR bundles that dependency; that **proves self-containment for the Java runtime classpath**, not that the application needs no database, network, or environment configuration.
- You might try building `catalog-app` from a checkout containing only the application module without a published parent/dependency; the resulting Maven/Gradle resolution failure proves **building from source still has coupling**.

This lesson shows how to **select a single module to build**, read the real **dependency graph**, package, and **verify the resulting product independently**. Two build options are covered: Maven Reactor and Gradle Multi-Project. Java 17 and Spring Boot 3.3.13 examples are kept consistent; use versions matching your project's policies when applying in practice.

## 1. Understand Three Kinds of "Independence" Before Running Commands

| Kind of Independence | Question to Answer | Right Evidence |
| --- | --- | --- |
| **Build scope** | Can you target a single module instead of building/testing the entire repository? | Maven `-pl`, Gradle task path `:module:build`, logs of selected tasks/reactor |
| **Source buildability** | Can the module compile without sibling module sources? | Parent/config and all dependencies already published or properly supplied; test against a controlled clean repo/cache |
| **Runtime artifact self-containment** | Can the app artifact run on a machine having only a compatible JVM and required config? | Inspect `BOOT-INF/lib`/manifest; copy just the executable JAR to another directory; `java -jar` + smoke test |

An additional dimension is **system/operational independence**: does the application avoid needing external services or handle their outages gracefully? That is a broader architectural question and is **not proven merely by a build or a single successful `java -jar` run**.

### Distinguishing Four Commonly Used Terms

- **Module:** a build unit (Maven project / Gradle subproject) with its own sources, dependencies, and outputs.
- **Aggregator:** a Maven POM with `<packaging>pom</packaging>` listing `<modules>`, or Gradle root/settings listing `include(...)`. It groups multiple modules into one build.
- **Dependency:** one module needs classes/artifacts from another module. For instance, `catalog-app → catalog-core` is an actual relationship, not "being in the same folder".
- **Product/artifact:** the published/deployed JAR/WAR. It can be a **plain library JAR** or a **Spring Boot executable JAR** carrying the Boot Loader and runtime dependencies.

When asked to "build a single module and verify independence", do not reply merely with "`mvn -pl` succeeded". Verify **the exact layer the requester cares about**.

## 2. Sample Maven/Gradle Multi-Module Diagram

We build two modules:

```text
multi-module-demo/
├── pom.xml                           (Maven aggregator + parent)
├── catalog-core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/example/catalog/core/
│       │   └── GreetingFormatter.java
│       └── test/java/dev/example/catalog/core/
│           └── GreetingFormatterTest.java
└── catalog-app/
    ├── pom.xml
    └── src/
        ├── main/java/dev/example/catalog/app/
        │   ├── CatalogApplication.java
        │   └── GreetingController.java
        └── test/java/dev/example/catalog/app/
            └── GreetingControllerTest.java
```

With Gradle, replace the three `pom.xml` files with `settings.gradle`, root `build.gradle`, and a `build.gradle` in each module, keeping the Java files identical.

Application dependency graph:

```text
              multi-module-demo
                 [root build]
                      |
              +-------+--------+
              |                |
         catalog-core      catalog-app
         [Java library]    [Boot service]
              ^                |
              +----------------+
                 app depends on core
```

**Crucial relationship:** `catalog-app` needs `catalog-core`. `catalog-core` does **not** depend on `catalog-app`. When you only want to test `core`, you do not need to start `app`. When building `app`, `core` must come from **the same reactor/multi-project build** or from a **repository containing the matching artifact**.

### Expected Observable Outcomes

When the example runs properly:

- `catalog-core` produces a **plain JAR** containing `dev.example.catalog.core.GreetingFormatter`.
- `catalog-app` produces an **executable Spring Boot JAR** with `app`'s `BOOT-INF/classes` and dependency `BOOT-INF/lib/catalog-core-1.0.0.jar`.
- HTTP `GET /hello` returns `Hello, Ada!`; `GET /hello?name=Linh` returns `Hello, Linh!`.
- Moving just `catalog-app-1.0.0.jar` outside the source tree still lets the app find `GreetingFormatter` via the nested `catalog-core` library.
- Without `core` available at build time, selecting only `app` **does not magically make** `app`'s source independent; Maven/Gradle must still resolve the artifact.

## 3. Shared Java Code for Both Maven and Gradle

The four main classes and two tests below are **complete files**. Place sources at their corresponding package paths.

### 3.1. Library `catalog-core`

`catalog-core/src/main/java/dev/example/catalog/core/GreetingFormatter.java`:

```java
package dev.example.catalog.core;

public final class GreetingFormatter {

    public String render(String name) {
        return "Hello, " + name + "!";
    }
}
```

The class does not use Spring, so the `core` module can remain a pure Java library. Separating `core` this way avoids applying Spring Boot `repackage` to a library that other modules need to import.

`catalog-core/src/test/java/dev/example/catalog/core/GreetingFormatterTest.java`:

```java
package dev.example.catalog.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {

    @Test
    void formatsGreeting() {
        GreetingFormatter formatter = new GreetingFormatter();
        assertEquals("Hello, Ada!", formatter.render("Ada"));
    }
}
```

This test proves **`core` compiles and passes tests by itself** with the test dependencies defined in its module. It does not prove `core` has zero external dependencies in real projects; the example deliberately uses only the JDK and JUnit at test time.

### 3.2. Spring Boot Application `catalog-app`

`catalog-app/src/main/java/dev/example/catalog/app/CatalogApplication.java`:

```java
package dev.example.catalog.app;

import dev.example.catalog.core.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Why declare `@Bean`? The `core` module uses package `dev.example.catalog.core`, which lies **outside** subpackages of `dev.example.catalog.app`; default component scanning from `CatalogApplication` does not scan unrelated packages merely because both modules share a repository. The example explicitly registers `GreetingFormatter` from `core` so the dependency and bean wiring are clear.

`catalog-app/src/main/java/dev/example/catalog/app/GreetingController.java`:

```java
package dev.example.catalog.app;

import dev.example.catalog.core.GreetingFormatter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingFormatter formatter;

    public GreetingController(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "Ada") String name) {
        return formatter.render(name);
    }
}
```

This endpoint needs no database or external API calls, making it easy to verify when running the artifact in an isolated folder. In production, a service may require external configuration, secrets, networking, and backend services.

`catalog-app/src/test/java/dev/example/catalog/app/GreetingControllerTest.java`:

```java
package dev.example.catalog.app;

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
class GreetingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void usesCodeFromCoreModule() throws Exception {
        mvc.perform(get("/hello").param("name", "Linh"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Linh!"));
    }
}
```

The app test confirms `app` **resolved, compiled, and invoked `core`'s API** on the test classpath. However, like any `@SpringBootTest`, this does not prove the **packaged JAR** runs properly; you still must run `java -jar` after building.

## 4. Maven: Configuring the Root Aggregator/Parent

Maven calls the set of modules in a single build run a **reactor**. A root aggregator lists `<modules>`; modules inherit a parent to share version/dependency management. The aggregator and parent roles can reside in the same POM, though conceptually they are distinct.

`multi-module-demo/pom.xml`:

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
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>catalog-core</module>
        <module>catalog-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

Several key details:

- `packaging=pom`: the root is an aggregator/parent, **not** a Spring Boot app needing `repackage`.
- `<modules>`: tells the Maven reactor about both modules so it can build them according to actual dependencies.
- `spring-boot-starter-parent`: supplies the BOM and plugin management aligned with Boot 3.3.13, including test conventions and Java 17 compiler settings.
- Do **not** declare `spring-boot-maven-plugin` under `<build><plugins>` at root, avoiding unwanted `repackage` execution inheritance into `catalog-core`. Only the app has an executable main class.

The Maven reactor orders builds based on real project dependencies, parent relationships, and build configuration. **Module listing order is not a replacement for dependency declarations**. If `catalog-app` imports classes from `core`, it must explicitly declare a dependency on `catalog-core`.

## 5. Maven: POMs for `core` and `app`

### 5.1. `catalog-core/pom.xml` — Library JAR

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Maven uses `jar` packaging to produce `catalog-core-1.0.0.jar`, containing only `core`'s app-independent classes/resources and standard metadata. JUnit in `test` scope **never** becomes a runtime dependency of `catalog-app` through `core`.

Notably, `core` does **not** declare the Spring Boot Maven Plugin. Passing an executable Boot JAR (which puts classes under `BOOT-INF/classes`) as a dependency to another module is a classic packaging mistake: consumers need a library JAR with compiled classes at the package root.

### 5.2. `catalog-app/pom.xml` — Boot Application

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>catalog-core</artifactId>
            <version>${project.version}</version>
        </dependency>

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
```

`${project.version}` resolves to `app`'s version `1.0.0`, matching `core` in this example. Real projects can version each module independently, in which case you must use the published version or a dedicated property/version catalog; modules do not all have to share one version.

The `catalog-core` entry in `<dependencies>` is the **real code-usage relationship**. The Maven reactor supplies `core`'s artifact when both modules are in the build; if building only `app` without `core`, Maven must resolve `dev.example:catalog-core:1.0.0` from an accessible cache/repository.

The Spring Boot Maven Plugin sits only in `app`, so the `repackage` goal converts the application JAR into an executable archive with nested dependencies. With the starter parent at root, `repackage` execution is managed automatically when `app` declares the plugin.

## 6. Maven Reactor: Building One Module Properly

Open a terminal at the **root `multi-module-demo`** containing the aggregator `pom.xml`. You need JDK 17 and a compatible Maven, or the Maven Wrapper if provided by the repository.

### 6.1. Build the Entire Repository

```bash
mvn -version
mvn clean verify
```

This command walks through the root POM, `core`, and `app`. `verify` runs prior phases including `package`; the Spring Boot Maven Plugin in `app` runs `repackage`, producing an executable JAR for `app`.

This is a useful **baseline** for verification before optimizing build scope. If a repository contains many unrelated modules, a full build can take a long time.

### 6.2. Selecting Only `app` — Needs `-am` When Siblings Are Not Yet Published

```bash
mvn -B -pl :catalog-app -am clean verify
```

Flag breakdown:

- `-B`: batch mode, suited for CI; unrelated to module selection directly.
- `-pl`/`--projects`: specifies the target project in the reactor. `:catalog-app` selects by **artifactId**, whereas `-pl catalog-app` typically selects by **relative path**.
- `-am`/`--also-make`: also builds **required module dependencies** in the reactor. Here `catalog-core` is built because `app` needs it; the root parent/aggregator may also participate per the reactor model.
- `clean verify`: cleans and builds/tests selected projects; this does not mean every module in the repository gets tested.

Conceptual execution order:

```text
multi-module-demo [pom]
       |
       v
catalog-core [jar]
       |
       v
catalog-app [jar + Boot repackage]
```

If the project also had an unrelated `unrelated-reporting` module, `-pl :catalog-app -am` would not pull it in merely because it appears in `<modules>`.

**Important point:** `-am` proves Maven computes the dependency graph accurately and builds **only needed modules**, not that `app` has no dependency on `core`.

### 6.3. Building Only `core` to Confirm the Upstream Boundary

```bash
mvn -B -pl :catalog-core -am clean verify
```

In our example, this tests `core` without compiling `app`. That matches the unidirectional graph `app → core`. In a real project, if `core` unexpectedly pulls in `app`, that signals coupling or a dependency cycle to fix.

### 6.4. `-amd` Goes in the **Opposite** Direction from `-am`

```bash
mvn -B -pl :catalog-core -amd test
```

`-amd`/`--also-make-dependents` expands selection to modules **that depend on** `core`, such as `catalog-app`. It helps when you change `core`'s API and want to evaluate consumers in the reactor. Note, however:

- `-amd` does not serve the same goal as `-am`; one selects **upstream dependencies**, while the other selects **downstream dependents**.
- For tests depending on reactor artifacts, Maven may need related modules built appropriately; with complex dependency graphs, pick phases/scopes carefully, potentially combining `-am` or running a broader reactor build.
- Never mistake `-amd` for an optimization to package only `app`; its purpose is downstream impact verification.

### 6.5. `-pl` Without `-am`: Why Can It "Pass Sometimes, Fail Other Times"?

```bash
mvn -B -pl :catalog-app clean verify
```

This command selects only `app`. If `catalog-core:1.0.0` is **not in the selected reactor or an accessible repository**, Maven fails dependency resolution. If a developer machine previously ran `mvn install` for `core`, the command can **succeed via the local Maven repository**, hiding the issue until it breaks on a fresh CI agent.

That is why a passing `mvn -pl :catalog-app verify` on your laptop is never proof that "app is completely independent". The build may have used an old `core` artifact from `~/.m2/repository` rather than the `core` source code currently being edited.

**Recommended default command in a monorepo before siblings are published:** `mvn -pl :catalog-app -am clean verify`.

## 7. Building `app` Without Rebuilding `core` Source: Requires a Pre-Built Artifact

This differs from a reactor subset build. A team might want to:

1. Build and publish `catalog-core` first.
2. Then build `catalog-app` solely against the **published artifact version**, without compiling `core` sources in the same run.

### Controlled Test in a Local Repository

From root, run:

```bash
# Step 1: install parent and catalog-core into the local Maven repository.
mvn -B -pl :catalog-core -am clean install

# Step 2: build only app; omit -am.
mvn -B -pl :catalog-app clean verify
```

Step 1 places the POM/artifact of the parent and `core` into the local Maven repository; Step 2 resolves `core` from there without recompiling `catalog-core`'s sources. This is a **module-only source build enabled by an installed artifact**, not proof that `app` has no dependency.

In real CI, prefer publishing `core`/parent to a managed artifact repository or running the reactor in one workflow. `mvn install` is **local**; other CI agents do not see it. When `core` evolves per commit with the same version, avoid installing stale artifacts into a shared local cache and assuming `app` builds against fresh code.

### Three Separate Experiments

| Experiment | How Is `core` Dependency Supplied? | Valid Conclusion |
| --- | --- | --- |
| `mvn -pl :catalog-app -am clean verify` | Reactor builds `core` sources in this run | Targeted reactor build succeeded |
| `mvn -pl :catalog-app clean verify` after `install`ing `core` | Local Maven repository | `app` builds when `core` artifact is already installed |
| Building `app` on a clean machine/CI with only `app` source | Artifact repository + valid parent/plugin/config | `app` builds from source independently of `core` checkout if all inputs are published |

In the third experiment, the **parent POM path** also matters. In our example, `app` has `<parent>dev.example:multi-module-demo:1.0.0</parent>` with `relativePath=../pom.xml`. If `catalog-app` is checked out separately from root, Maven needs the parent POM in a repository and may require adjusting `relativePath` for valid lookup (commonly `<relativePath/>` when the parent is published). **Copying only the `app` folder does not bring enough build config**.

If long-term standalone checkout building is the goal, design release/versioning, repository credentials, plugin versions, parent/BOM publishing, and lock down external dependencies. Never patch a POM temporarily for one test and call that reproducible proof.

## 8. Module Graph vs Dependency Graph: Inspecting What `app` Actually Uses

The Maven reactor shows **which modules build**; the Maven dependency plugin shows **which artifacts enter the dependency tree**. These are two different views.

From root:

```bash
mvn -pl :catalog-app -am dependency:tree
```

Exact output depends on plugin and Maven versions; key expected dependencies:

```text
dev.example:catalog-app:jar:1.0.0
+- dev.example:catalog-core:jar:1.0.0:compile
+- org.springframework.boot:spring-boot-starter-web:jar:3.3.13:compile
\- org.springframework.boot:spring-boot-starter-test:jar:3.3.13:test
```

This is a **simplified diagram**, not exact stdout, because the tree also includes many transitive entries whose formatting and versions depend on the tool. To filter only for `core`:

```bash
mvn -pl :catalog-app dependency:tree -Dincludes=dev.example:catalog-core
```

What to verify is that **`core` appears in `compile` scope**. When `spring-boot:repackage` builds the executable app JAR, `core`'s plain JAR is placed inside `BOOT-INF/lib` (unless explicitly excluded or customized).

**Do not assume from the dependency tree that every dependency is guaranteed to be packaged:** `provided`, `optional`, exclusions, plugin packaging rules, and dependency conflicts can change the output. You must **inspect the actual archive**.

## 9. Building, Inspecting, and Running `app`'s Spring Boot Artifact Alone

From the repository root:

```bash
mvn -B -pl :catalog-app -am clean verify
```

The example Maven build creates:

```text
catalog-core/target/catalog-core-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar
catalog-app/target/catalog-app-1.0.0.jar.original
```

**Distinguish:**

- `catalog-core-1.0.0.jar` is the **library JAR**: `GreetingFormatter` sits at the package root.
- `catalog-app-1.0.0.jar` is the **Spring Boot executable JAR** after repackage: Boot Loader, `BOOT-INF/classes`, `BOOT-INF/lib`.
- `catalog-app-1.0.0.jar.original` is the plain app JAR before repackaging; it does **not** carry runtime dependencies in executable Boot layout and is not the main deployment file.

### 9.1. Inspect Archive Entries

```bash
jar tf catalog-core/target/catalog-core-1.0.0.jar
jar tf catalog-app/target/catalog-app-1.0.0.jar
```

In the `core` JAR you should see:

```text
dev/example/catalog/core/GreetingFormatter.class
```

In the Boot app JAR you should see representative entries:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/catalog/app/CatalogApplication.class
BOOT-INF/classes/dev/example/catalog/app/GreetingController.class
BOOT-INF/lib/catalog-core-1.0.0.jar
BOOT-INF/lib/spring-boot-3.3.13.jar
```

These are **entries to look for in the long output**, not the full `jar tf` listing. Other dependencies carry resolved versions matching the BOM. `core` classes do **not** have to sit directly under `BOOT-INF/classes/dev/example/catalog/core/`: they belong inside the nested JAR `BOOT-INF/lib/catalog-core-1.0.0.jar`. That is the right packaging structure.

### 9.2. Test Running Without the Source Tree

Create an empty directory **outside the repository**, copy just the executable app JAR into it, and launch from there. Linux/macOS:

```bash
mkdir -p /tmp/catalog-artifact-test
cp catalog-app/target/catalog-app-1.0.0.jar /tmp/catalog-artifact-test/
cd /tmp/catalog-artifact-test

java -jar catalog-app-1.0.0.jar --server.port=18080
```

Run these after building at root; use an isolated folder lacking `catalog-core/`, `catalog-app/src/`, or `target/`. If `/tmp` is not writable in your environment, choose another permitted temporary folder.

PowerShell on Windows:

```powershell
New-Item -ItemType Directory -Force -Path "$env:TEMP\catalog-artifact-test" | Out-Null
Copy-Item ".\catalog-app\target\catalog-app-1.0.0.jar" "$env:TEMP\catalog-artifact-test\"
Set-Location "$env:TEMP\catalog-artifact-test"

java -jar catalog-app-1.0.0.jar --server.port=18080
```

Open a **second terminal** once the app logs successful startup:

```bash
curl -fsS http://localhost:18080/hello
curl -fsS "http://localhost:18080/hello?name=Linh"
```

The two HTTP response bodies, in order:

```text
Hello, Ada!
Hello, Linh!
```

Proof: the executable JAR runs on the JVM without Maven at runtime and without `core`'s source folder on disk. `GreetingFormatter` loads from the nested `core` JAR inside the app artifact.

**Inference limits:** this test does not guarantee production shares the same JDK, networking, environment variables, secrets, databases, or timezone. Because the example has no external integrations, results are intentionally easy to reproduce; real systems need smoke tests and deployment checks matching their contracts.

### 9.3. Avoid Confusing Local-Cache Presence with Archive Presence

When running `java -jar` in an isolated folder, the app **does not ask Maven to read `~/.m2` to load classes**. If the JAR lacks `catalog-core`, the test will fail once the app needs `GreetingFormatter`; having `core` in the local Maven repository **cannot save** the executable JAR's runtime.

This is the critical gap between:

- Maven build resolving dependencies from repositories to **assemble an artifact**, and
- JVM/Boot Loader loading **packaged dependencies** to run an artifact.

## 10. Verifying Artifact Self-Containment with a Small CI Gate

A pipeline should check both structure **and** behavior. On Linux/macOS with JDK `jar` and `grep`, at root:

```bash
set -e

APP="catalog-app/target/catalog-app-1.0.0.jar"

jar tf "$APP" | grep -q '^BOOT-INF/classes/dev/example/catalog/app/CatalogApplication.class$'
jar tf "$APP" | grep -q '^BOOT-INF/lib/catalog-core-1.0.0.jar$'
jar tf "$APP" | grep -q '^org/springframework/boot/loader/launch/JarLauncher.class$'

echo "PASS: app classes, core library and Boot loader are packaged"
```

When all conditions match, stdout from this check is:

```text
PASS: app classes, core library and Boot loader are packaged
```

The commands above use the **example's** JAR names; when module versions change, derive the artifact path/name from build metadata instead of hardcoding permanently. Also inspect the manifest:

```bash
unzip -p catalog-app/target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
```

Look for:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.catalog.app.CatalogApplication
```

Other manifest fields may appear. **Structural gates do not replace `java -jar` smoke tests.** A JAR with all expected entry names can still fail startup due to config errors, version mismatches, or other missing dependencies.

### Safer CI Smoke Test Recommendations

- Run inside an isolated container/VM using a port that does not collide with active workloads.
- Launch `java -jar` as a lifecycle-managed process and poll the health/HTTP endpoint with a CI-controlled timeout.
- On pass or fail, stop the process, capture logs, and record the artifact checksum.
- Once verified, publish the **exact tested file**; do not rebuild with another profile/dependencies and swap files at the deploy stage.
- Avoid leaving indefinite background servers running in shells without cleanup/timeouts.

The anchor is the **exact artifact ID**. If tooling builds a Docker image from a layered JAR, verify the image is built from the exact executable JAR that passed the gate and uses a compatible JVM/base image.

## 11. Gradle Multi-Project: Same Graph, Different Build Selection Than Maven

Gradle calls modules **subprojects**. `settings.gradle` declares module paths, while `implementation project(':catalog-core')` creates a project dependency from `app` to `core`. When requesting a task on `app`, Gradle **automatically pulls the required `core` tasks into the task graph**.

Key differences from Maven:

- Maven uses project selector `-pl` and reactor flags `-am`/`-amd`.
- Gradle uses **fully qualified task paths** such as `:catalog-app:build`.
- Gradle project dependencies wire directly into the task graph; no `-am`-style flag is needed in standard usage.

Below is the **alternative build configuration to Maven**, reusing the four Java classes and two tests from section 3.

### 11.1. `settings.gradle` at Root

```groovy
rootProject.name = 'multi-module-demo'

include 'catalog-core', 'catalog-app'
```

### 11.2. `build.gradle` at Root

```groovy
allprojects {
    group = 'dev.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

Root only shares group, version, and repository in the example; it does not apply the Spring Boot plugin to all subprojects.

### 11.3. `catalog-core/build.gradle`

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Module `core` gets `jar` and `test` tasks from the Java Library plugin. It has **no** `bootJar` because it does not apply the Spring Boot plugin. Test dependencies stay inside test configurations and do not leak to `app`.

### 11.4. `catalog-app/build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':catalog-core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'dev.example.catalog.app.CatalogApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot Gradle Plugin and Dependency Management Plugin coordinate to apply the BOM matching the Boot release, so starters omit explicit versions in the example. Putting the Boot plugin on **app** rather than `core` keeps `core` producing a plain library JAR consumable via standard classpaths.

### 11.5. Selecting Tasks Per Module

If the repository has a Gradle Wrapper compatible with Spring Boot 3.3, from root:

```bash
./gradlew projects
./gradlew :catalog-core:build
./gradlew :catalog-app:build
./gradlew :catalog-app:bootJar
```

On Windows use `gradlew.bat`. If there is no Wrapper yet, install/generate a compatible Gradle version; do not assume every repository contains `gradlew`.

Meaning:

- `:catalog-core:build`: builds and tests `core`, with no reason to run `app` tests.
- `:catalog-app:build`: selects `app`'s lifecycle task, yet **still runs upstream tasks in `core`** to supply dependency artifacts/classes.
- `:catalog-app:bootJar`: packages the executable app JAR and runs tasks needed to supply the `core` artifact; **does not guarantee `core` tests run** if the task graph does not require them.
- `./gradlew build` from root acts as a **task selector** running `build` across relevant subprojects, unlike the fully qualified path `:catalog-app:build`.

Preview the task graph without building:

```bash
./gradlew :catalog-app:build --dry-run
```

`--dry-run` shows which tasks are scheduled and **creates no new artifacts**, so run an actual build before inspecting files.

### 11.6. Inspecting Gradle Runtime Dependencies

```bash
./gradlew :catalog-app:dependencies --configuration runtimeClasspath
./gradlew :catalog-app:dependencyInsight --dependency catalog-core --configuration runtimeClasspath
```

Output should show `app` resolving project dependency `:catalog-core`. It may appear as a **project dependency/variant** rather than a repository binary JAR name like Maven. The build tool selects the matching variant for the consumer, potentially accompanied by compile/jar tasks.

Gradle uses incremental compilation, build cache, configuration cache, and task avoidance. Thus "a task did not execute this run" **does not mean the module is independent**; the task may simply be `UP-TO-DATE` or restored from cache. To test after a clean build, run `./gradlew clean :catalog-app:build` (which performs a broad clean) or use a controlled clean workspace/cache per reproducibility requirements.

### 11.7. Inspecting the Gradle-Built Boot JAR

With the example's version/names, artifacts normally live at:

```text
catalog-core/build/libs/catalog-core-1.0.0.jar
catalog-app/build/libs/catalog-app-1.0.0.jar
catalog-app/build/libs/catalog-app-1.0.0-plain.jar
```

Two key notes:

- `catalog-core-1.0.0.jar` is the plain library, containing no Boot Loader.
- `catalog-app-1.0.0.jar` is the Boot executable archive; its contents should include `BOOT-INF/lib/catalog-core-1.0.0.jar` and compiled app classes.
- `catalog-app-1.0.0-plain.jar` is the output of the `jar` task with classifier `plain` per Boot Gradle Plugin convention. Never use this plain JAR to judge standalone deployability.

Inspect:

```bash
jar tf catalog-app/build/libs/catalog-app-1.0.0.jar
java -jar catalog-app/build/libs/catalog-app-1.0.0.jar --server.port=18080
```

Call `curl` in another terminal once running, just as in section 9. You can copy the Gradle JAR into an isolated folder to test without sibling module sources.

## 12. What Does "Build App Alone" Mean in Gradle?

`implementation project(':catalog-core')` means `app` uses a **project dependency**, not an independently published binary module. Therefore:

```bash
./gradlew :catalog-app:build
```

is **not** equivalent to cutting `catalog-app` out of the monorepo and expecting Gradle to build it with the current `build.gradle`. Once separated, `settings.gradle` no longer declares `:catalog-core`, and `project(':catalog-core')` fails to resolve.

To develop/publish `app` independently from `core` sources:

1. Build and publish `catalog-core` (plain JAR with POM/module metadata and transitive dependencies) to a valid artifact repository.
2. Switch `app`'s dependency from a **project dependency** to an **external module dependency** with an explicit version.
3. Ensure repository credentials, BOM/plugin versions, and all build inputs are accessible in a fresh checkout/workspace.
4. Build `app` in a clean environment and observe resolved artifacts/versions.

Replacement Gradle snippet in `catalog-app/build.gradle` once `core` has been published:

```groovy
dependencies {
    implementation 'dev.example:catalog-core:1.0.0'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is only a **replacement fragment for `dependencies`**, not a complete build script; the repository must actually hold `dev.example:catalog-core:1.0.0`. Do not keep both `implementation project(':catalog-core')` and `implementation 'dev.example:catalog-core:1.0.0'` without a clear resolution strategy, as doing so can put the same code onto the classpath via two routes.

**Do not modify the build model of the project-dependency example before completing the `:catalog-app:build` experiment**; the two setups represent different scenarios for understanding "independence".

## 13. Levels of Independence That Must Not Be Equated

### 13.1. Building One Target Is Not "Compiling Without Upstreams"

In Maven, `-pl :catalog-app -am` builds `core` as an upstream dependency. In Gradle, `:catalog-app:build` runs `:catalog-core:compileJava`/`jar` via the task graph. Both are **targeted builds**, not "app does not use core".

### 13.2. Having All Java Classes Does Not Mean Independence from External Services

An executable JAR may bundle all of Spring Boot/Tomcat/Jackson and the core library, yet at runtime it still needs:

- A matching JVM version (e.g., Java 17).
- Suitable environment variables and configuration sources.
- Databases, message brokers, caches, or HTTP services if the app calls them.
- Required filesystem paths, mounted volumes, TLS certificates, or native libraries.
- Proper ports, DNS, network policies, resource quotas, and operational permissions.

**"Self-contained JAR" has a narrow meaning:** primarily carrying the Java code/dependencies needed by the launcher; it is not a virtual machine, container image, or self-sufficient business system needing nothing external.

### 13.3. Which Modules Get Tested Is a Separate Question

`mvn -pl :catalog-app -am test` can run tests in both `core` and `app` per reactor selection. With Gradle, `:catalog-app:build` runs `app` tests yet **does not promise to run all `core` tests**: upstream tasks mainly produce dependency outputs and may omit `:catalog-core:test`. When changing `core` APIs or behavior, CI should gate on both `core` tests and consumer tests.

### 13.4. "Works on My Machine" Is Not Reproducibility

A passing local build may depend on:

- `~/.m2`/Gradle cache holding unpublished internal artifacts.
- Leftover `target/`/`build/` outputs from earlier builds.
- SNAPSHOT dependencies resolved at different times.
- JDK/toolchain, plugin versions, environment, or build profiles differing from CI.
- Hidden dependency graph conflicts or accidental exclusions.

To assess reproducibility, version the Wrapper, pin dependency versions by policy, use clean environments, verify checksums, and track provenance. **Never call a build "independent" simply because dropping `-am` still passes thanks to a local cache.**

## 14. Diagnosing Common Errors

| Symptom | Possible Cause | Verification & Resolution |
| --- | --- | --- |
| `mvn -pl :catalog-app package` fails to resolve `catalog-core` | `core` not in selected reactor and absent from repositories | Add `-am` or publish/install `core` first; never delete the dependency |
| `mvn -pl :catalog-app ...` passes on laptop yet fails on CI | Local Maven cache holds old `core`/parent versions | Build from a clean repo, use `-am`, or use a managed artifact repository |
| `mvn -pl :catalog-core -am verify` still builds `app` | Selection or parent/aggregator config differs from expectations | Check exact command, Maven reactor summary, and dependency graph |
| `core` changed yet `app` shows old behavior | Resolved from local repo or cached version instead of fresh `core` source | Check artifact coordinates, reactor selection, dependency tree, and timestamps/versions |
| `app` uses `core`'s `@Component` yet fails to inject | `core` package is outside component scan, or implementation missing from package | Configure valid bean/scan; inspect dependency JAR and runtime classpath |
| Gradle `:catalog-app:build` runs tasks in `core` | `implementation project(':catalog-core')` creates task dependencies | Expected behavior; do not confuse targeted builds with zero upstream work |
| Gradle reports `Project with path ':catalog-core' could not be found` | Split `app` out of `settings.gradle` while still using a project dependency | Publish `core` and switch to external module coordinates, or keep multi-project settings |
| Gradle task `:catalog-core:jar` reports `UP-TO-DATE` | Incremental build / build cache | Inspect task graph and inputs; run clean/cache-controlled build if needed |
| App Boot JAR lacks `BOOT-INF/lib/catalog-core-...jar` | Dependency excluded/wrong scope, picked plain app JAR, or altered plugin config | Inspect `jar tf` and app dependency graph; pick exact `bootJar`/`repackage` output |
| `java -jar` throws `NoClassDefFoundError` from `core` | `core` omitted from app JAR or classpath altered | Check nested library JAR, version, and Boot loader; rebuild with plugin |
| Plain `core` JAR contains `BOOT-INF/classes` | Boot plugin repackaged library by mistake | Keep `core` as plain `jar`; apply Boot plugin only to `app` |
| `java -jar catalog-app...jar` works at root yet fails in another directory | Relative file/resource paths or config depend on working directory | Use classpath resources or explicit external config; avoid non-portable repo paths |
| Artifact runs locally yet fails to connect to production DB | External config/network/secrets differ | Do not generalize from classpath checks; inspect deployment dependencies, health, and credentials |
| Multiple versions of `catalog-core` inside app JAR | Duplicate dependency declarations, mixed project/external coordinates, or custom packaging | Inspect `BOOT-INF/lib` and dependency tree; resolve conflicts and pin versions |
| After changing classifier, pipeline deploys `-plain.jar` | Script relies on globs/filenames | Select exact `bootJar` or `spring-boot:repackage` output; verify manifest |

### Recommended Debugging Sequence

1. Read the **exact command**: which Maven `-pl`/`-am` or Gradle task path ran?
2. Inspect the **graph**: which module depends on which, and with what versions/scopes/variants?
3. Identify the **right artifact**: core library JAR vs app executable JAR, name/version/classifier.
4. Run a **clean targeted build** from root with the right selection.
5. Check **per-module test results**, not only the overall summary.
6. Inspect **JAR contents**: app classes, core library, Boot Loader, and manifest.
7. Copy the app JAR to a **directory without repository sources** and run `java -jar`.
8. If source independence is the goal, test on a clean environment with **published parent and core artifacts**, using no leftover sources or caches.
9. Retain **artifact checksums**, CI logs, runtime smoke test outputs, and dependency scan results.

## 15. Self-Check Scenarios

**Scenario A.** Running `mvn -pl :catalog-app -am clean verify` succeeded. Does that prove `app` does not depend on `core`?

*Answer:* No. `-am` is specifically the flag instructing Maven to build upstream dependencies in the reactor, including `core`. The valid conclusion is that building the related module set succeeded.

**Scenario B.** `mvn -pl :catalog-app verify` passed after a prior `mvn install` on a personal laptop. Have you proven an independent build?

*Answer:* It proves only that `app` can resolve the `core` artifact already installed in the local repository. To verify independent source builds, you need a repository supplying the parent/`core` and a clean environment, and must confirm the exact version consumed.

**Scenario C.** `./gradlew :catalog-app:build` still prints `:catalog-core:compileJava`. Did Gradle ignore the request to build only `app`?

*Answer:* No. You selected `app`'s lifecycle task, and project dependency `core` is built because it is a required input for `app` to compile/run. That task graph is the right behavior.

**Scenario D.** The app executable JAR contains `BOOT-INF/lib/catalog-core-1.0.0.jar`. Can it run on a server without `core`'s source code?

*Answer:* Likely yes, provided the remaining JVM, config, and external dependencies match. In a standard Spring Boot executable JAR, the `core` library is already bundled. Copy that exact file to an isolated environment, launch it, and smoke test rather than relying solely on entry names.

**Scenario E.** Should you apply Spring Boot Maven Plugin `repackage` to both `catalog-core` and `catalog-app` for "consistency"?

*Answer:* No. `core` is a plain library JAR consumed by `app`; executable Boot archives place classes under `BOOT-INF/classes` and do not substitute for ordinary library artifacts. Only `app` (which has the main method) needs `repackage`.

**Scenario F.** `core` has JUnit tests, and Gradle `:catalog-app:build` passes. Can you be sure `core`'s tests ran?

*Answer:* No. A project dependency schedules the compile/jar tasks needed by `app`, without forcing `:catalog-core:test`. CI must run `core` tests explicitly or target a task graph that includes them.

**Scenario G.** The app JAR was copied elsewhere, `java -jar` starts, yet the service cannot connect to Redis in deployment. Is the app "not independent"?

*Answer:* For the Java classpath, the artifact is self-contained; operationally, it still depends on Redis and config/networking. Always state **which independence criterion** is under test rather than conflating the two.

**Scenario H.** You need to build `core` and its consumers to catch API breakages after editing `core`. Which Maven option do you use?

*Answer:* `-pl :catalog-core -amd` selects dependents in the reactor. Depending on the graph and lifecycle, combine with required dependency modules and test phases, and inspect the actual reactor log.

**Scenario I.** You want to split `catalog-app` into its own repository, while `build.gradle` still has `implementation project(':catalog-core')`. What must change?

*Answer:* Publish `core` as a versioned artifact, switch to `implementation 'dev.example:catalog-core:1.0.0'`, configure repositories, and reserve project dependencies for modules inside the same multi-project build.

**Scenario J.** Two CI jobs run on the same source yet produce different app JAR checksums. Can you conclude the module is not independent?

*Answer:* Not yet. Differences may come from timestamps, toolchains, SNAPSHOTs, dependency resolution, build metadata, or resource ordering. Investigate reproducibility specifically by checking dependency versions, archive config, and plugins.

## 16. Single-Module Product Acceptance Checklist

**Before building:**

- Identify the target module and both upstream and downstream dependency graphs.
- Pick Maven `-pl/-am` or a Gradle fully qualified task path; avoid building unrelated subprojects unintentionally.
- Verify Java toolchain, Spring Boot plugin, and internal module versions.
- Separate application modules from library modules; never repackage a library meant as a dependency.

**After building:**

- Only required modules/tasks ran; inspect the reactor summary / Gradle task graph.
- `core` and `app` tests ran per policy; never assume passing `app` tests mean sibling tests ran too.
- The `app` artifact is an **executable Boot JAR**, not a plain library JAR or `.jar.original`/`-plain.jar`.
- `jar tf` shows `BOOT-INF/classes`, `BOOT-INF/lib/catalog-core-...jar`, and the Boot Loader; manifest `Main-Class`/`Start-Class` are valid.
- No internal libraries were excluded, duplicated, or resolved to unintended versions.

**Post-build independence checks:**

- Copy the JAR to a clean directory without repository sources and run it on a compatible JVM.
- Smoke test the main endpoints or workflows, confirming `core` code actually executes.
- Document dependencies external to the JAR: env vars, secrets, databases, brokers, ports, filesystems, network, TLS.
- If source-build independence is required, test in a clean environment with **published parent/core artifacts** and no leftover sources or caches.
- Retain logs, dependency trees, artifact digests, and test evidence; CI deploys the exact file that passed QA.

**Conclusion:** **Building a single module separately** is a build-tool scoping action; it does not erase dependency relationships. **Java runtime artifact independence** is a separate property that must be verified by inspecting the executable JAR's contents and running it outside the repository. **Source-build independence from sibling repositories** additionally requires published dependencies/parents and clean-environment resolution of all build inputs. In Spring Boot multi-module projects, the practical approach is keeping **`core` as a plain library JAR** and **`app` as a Boot executable JAR**, using `-pl :app -am` or `:app:build` to build the right dependency graph, and proving the artifact via **archive inspection and smoke testing**.

### Official Documentation

- Apache Maven — Guide to Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Gradle — Structuring Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Use an Application as a Dependency: https://docs.spring.io/spring-boot/how-to/build.html