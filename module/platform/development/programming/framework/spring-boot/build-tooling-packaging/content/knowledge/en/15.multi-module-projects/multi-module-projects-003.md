# Building the Maven Reactor with `-pl`, `-am`, and Dependency Order

## 1. Goal: Build Only the Necessary Parts of a Multi-Module Spring Boot Project

In a large Java/Spring Boot project, each Maven module can produce its own artifact. A web application may use a business service module; the business service module may in turn use a core module. Running Maven manually across directories in an arbitrary order risks picking up stale artifacts from `~/.m2/repository` or failing to resolve dependencies.

The **Maven reactor** handles that coordination: Maven collects the projects in the reactor, sorts them according to dependency relationships, and runs lifecycles/goals for the selected set of projects.

Three most important flags:
- `-pl`/`--projects`: **select** one or more modules.
- `-am`/`--also-make`: together with `-pl`, **also build upstream modules** required by the selected modules.
- Reactor sorting: preserves a valid **dependency order**, rather than running strictly by the order of `<module>` lines in the POM.

Additional useful flags:
- `-amd`/`--also-make-dependents`: also build **downstream modules** that depend on the selected module.
- `-rf`/`--resume-from`: resume the reactor from a specific project after a failed build, though upstream artifacts must be verified.
- `-T`: enables parallel builds for independent branches when plugins/tests are thread-safe.

Frequently used command, run at the multi-module project root:

```bash
mvn -B -ntp -pl :boot-app -am clean package
```

This command focuses on building `boot-app` along with the local Maven modules it needs, in the proper order. `-B` enables batch mode and `-ntp` reduces artifact download logs. This lesson illustrates using **Maven 3.9.x, Java 17+, and Spring Boot 3.5.0**. These are fixed versions for the example and are **not a claim of the latest versions**. Maven 4 changes how root/subprojects are determined; when using Maven 4, consult the Maven 4 documentation rather than assuming every detail matches Maven 3.

## 2. Three Concepts to Keep Separate: Aggregator, Parent, and Dependency

### 2.1. Aggregator Defines Reactor Members

A root `pom.xml` has:

```xml
<packaging>pom</packaging>
<modules>
    <module>boot-app</module>
    <module>service-lib</module>
    <module>core-lib</module>
</modules>
```

`<modules>` is a list of **relative paths** to child project POMs; the reactor collects them. It does not say that `boot-app` depends on `service-lib`. Listing `boot-app` first also does not force Maven to build the app before the libraries if dependencies are declared properly.

A module can also act as an aggregator for deeper modules. With Maven 3, running from the aggregator root is the clearest way to select reactor projects with `-pl`.

### 2.2. Parent POM Defines Inherited Configuration

A child POM has:

```xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

`<parent>` is a **POM inheritance** relationship: the child can inherit versions, properties, dependency/plugin management, and compatible Maven configuration. It **does not** automatically add Java classes from every sibling module to the child's classpath.

The root can simultaneously be **both aggregator and parent**, yet the two concepts are not identical. An aggregator can collect modules that use separate parents; a corporate parent can solely manage configuration without declaring `<modules>`.

### 2.3. Dependency Creates the Library-Consumer Relationship

Suppose `service-lib` uses `core-lib`. In `service-lib/pom.xml`, there must be an actual dependency:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core-lib</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </dependency>
</dependencies>
```

This is an **instantiated project dependency** creating the constraint: `core-lib` must be ready before `service-lib`. Simply listing both modules under `<modules>` or placing `core-lib` inside `dependencyManagement` is not enough.

**Mental model:** the aggregator decides **which projects are collected**; inheritance decides **which configuration is inherited**; dependencies decide **which module needs which module's artifact**; the reactor decides the **build order and execution set**.

## 3. How Does the Reactor Collect, Sort, and Execute Projects?

The reactor operates in three steps:
1. **Collect:** reads the aggregator and module POMs, forming the set of Maven projects.
2. **Sort:** finds an order that satisfies dependency relationships, such as core before service, and service before application.
3. **Build:** executes the requested Maven lifecycle phases/goals on the selected projects.

Example graph:

```text
core-lib  ------>  service-lib  ------>  boot-app
  produces JAR       produces JAR         Boot executable JAR

A --> B means B needs A's artifact, so A must be built before B.

Root reactor-demo:
  parent POM of all modules
  packaging = pom, not an executable JAR
```

Even when `<modules>` lists `boot-app` before `service-lib` and `core-lib`, the reactor still enforces the valid order **root/parent → core-lib → service-lib → boot-app**.

### 3.1. Which Relationships Does Reactor Sorting Consider?

According to the Maven 3 guide, the reactor uses references that are **actually declared and used** within the reactor, including:

- A project `<dependency>` on an artifact produced by another module.
- A plugin declaration using a plugin built by another module in the reactor.
- A plugin dependency using an artifact from a module in the reactor.
- A build extension from another module in the reactor.
- A module's parent POM if the parent is also in the reactor.
- The order in `<modules>` when no higher-priority constraint applies.

Declaring something only in `<dependencyManagement>` or `<pluginManagement>` **does not** create an edge; those sections only manage default versions/configuration without proving the dependency/plugin is actually used.

### 3.2. Topological Order and Independent Branches

A directed acyclic dependency graph (DAG) can have multiple valid topological orders. For example:

```text
                +--> report-lib
core-lib -------|
                +--> audit-lib
```

`report-lib` and `audit-lib` do not depend on each other, so the reactor can process them in declaration order (or in parallel with `-T` when valid) once `core-lib` is ready. Never rely on "module X always runs third" if there is no dependency edge enforcing that exact position.

### 3.3. Circular Dependencies Are an Architectural Error

If `core-lib` declares a dependency on `service-lib` and `service-lib` also declares one back, the graph has a cycle:

```text
core-lib ---> service-lib ---> core-lib
```

No valid build order exists. Reordering `<modules>` or adding `-am` cannot fix a cycle. Extract shared APIs/contracts into a lower-level module, invert a dependency, or refactor responsibilities. Never work around it by manually installing an old JAR in the local repository, as that makes builds non-reproducible.

## 4. Complete Multi-Module Maven Example, Runnable with Java 17

We create 3 child modules:
- `core-lib`: Java library formatting greetings.
- `service-lib`: uses classes from `core-lib`.
- `boot-app`: Spring Boot web application calling `service-lib`, producing an executable JAR.

The root POM intentionally lists modules in **reverse dependency order** to observe reactor sorting in action.

### 4.1. Directory Structure

```text
reactor-demo/
├── pom.xml
├── core-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/core/GreetingFormatter.java
├── service-lib/
│   ├── pom.xml
│   └── src/main/java/com/example/service/GreetingService.java
└── boot-app/
    ├── pom.xml
    └── src/main/java/com/example/app/DemoApplication.java
```

You need Java 17 or higher, a Maven version compatible with Spring Boot 3.5.0, and repository access for Spring Boot artifacts/Maven plugins. Use your repo's Maven Wrapper if present; examples run with `mvn` for simplicity.

### 4.2. Root `reactor-demo/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactor-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>
    <name>Reactor Demo Parent</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <modules>
        <module>boot-app</module>
        <module>service-lib</module>
        <module>core-lib</module>
    </modules>
</project>
```

Explanation:
- `packaging=pom`: the root aggregates/inherits and does not attempt to build a Java JAR from the root.
- `<modules>` only collects members; the reversed order is intentional.
- The root inherits the Spring Boot starter parent for managed dependency/plugin versions and Java release defaults.
- The root **does not declare** `spring-boot-maven-plugin` inside `<build><plugins>`, because library modules should not repackage into executable Boot JARs.
- Child modules all inherit version `0.0.1-SNAPSHOT` from the root.

### 4.3. Module `core-lib`

**`core-lib/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
```

**`core-lib/src/main/java/com/example/core/GreetingFormatter.java`:**

```java
package com.example.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

This is a plain Java class. `core-lib` needs neither `@SpringBootApplication` nor the Spring Boot Maven Plugin. Maven produces the **plain JAR** `core-lib/target/core-lib-0.0.1-SNAPSHOT.jar`.

### 4.4. Module `service-lib`

**`service-lib/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>service-lib</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

**It is the `core-lib` dependency here that creates the reactor edge `core-lib → service-lib`**. The expression `${project.version}` is interpolated by Maven to the effective project version, which is `0.0.1-SNAPSHOT` in this demo.

**`service-lib/src/main/java/com/example/service/GreetingService.java`:**

```java
package com.example.service;

import com.example.core.GreetingFormatter;

public final class GreetingService {
    public String message(String name) {
        return GreetingFormatter.greet(name);
    }
}
```

If you remove `<dependency>core-lib</dependency>` from the service POM, the Java source will lack `com.example.core.GreetingFormatter` on the compile classpath even though both are siblings in the aggregator.

### 4.5. Module `boot-app`

**`boot-app/pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>reactor-demo</artifactId>
        <version>0.0.1-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>service-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Module `boot-app` declares a **direct** dependency on `service-lib`; the dependency on `core-lib` is brought in transitively through `service-lib`. `spring-boot-starter-web` provides Spring MVC and the embedded server. The Spring Boot Maven Plugin lives only in the app to produce an **executable JAR** from that module.

Because the root inherits `spring-boot-starter-parent`, the app module already gets the `repackage` execution when the plugin is declared. Library modules do not need this plugin; if placed in parent `build/plugins` and inherited by children, libraries may fail for lacking a main class or produce archives unsuitable as dependencies.

### 4.6. Actually Runnable Java Application

**`boot-app/src/main/java/com/example/app/DemoApplication.java`:**

```java
package com.example.app;

import com.example.service.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}

@RestController
class GreetingController {
    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "World") String name) {
        return service.message(name);
    }
}
```

There are two Java classes in the same file; only `DemoApplication` is `public`, so this is valid. `@Bean` registers `GreetingService` explicitly into the Spring context; the core/service libraries do not need to add Spring component scanning. `GreetingController` is discovered within the application's package and invokes the service chain.

HTTP flow:

```text
GET /hello?name=Lan
   -> GreetingController.hello("Lan")
      -> GreetingService.message("Lan")
         -> GreetingFormatter.greet("Lan")
            -> "Hello, Lan!"
```

This output verifies compilation, dependency resolution in the reactor, and the runtime classpath of the executable Boot JAR.

## 5. Run the Full Reactor and Verify Build Order

Standing at the **root `reactor-demo/`**:

```bash
java -version
mvn -version
mvn -B -ntp clean package
```

Maven reads the root aggregator, collects the three modules, and determines the build order. Even though the root declares `boot-app` first, the logical order that should appear in `Reactor Build Order` is:

```text
Reactor Demo Parent
core-lib
service-lib
boot-app
```

These are **illustrative lines showing project order/names**; actual logs also contain plugin goals, timestamps, progress, and `Reactor Summary` depending on Maven version. If parallel builds are enabled, logs from independent modules may interleave.

Typical artifacts after a successful build:

```text
core-lib/target/core-lib-0.0.1-SNAPSHOT.jar
service-lib/target/service-lib-0.0.1-SNAPSHOT.jar
boot-app/target/boot-app-0.0.1-SNAPSHOT.jar
```

The two library files are plain JARs. `boot-app` has been repackaged by Spring Boot, containing application classes in `BOOT-INF/classes` and runtime dependencies in `BOOT-INF/lib`.

Run the application:

```bash
java -jar boot-app/target/boot-app-0.0.1-SNAPSHOT.jar
```

From another terminal:

```bash
curl -fsS 'http://localhost:8080/hello?name=Lan'
```

**Exact response body:** `Hello, Lan!` (not necessarily with a trailing newline). If port 8080 is taken, you can pass `--server.port=9090` after the JAR file and adjust the curl URL accordingly. Stop the JVM with Ctrl+C before running other commands.

**Important point:** `mvn package` produces artifacts inside each `target` directory; it **does not automatically install** them into `~/.m2/repository`. A reactor build can consume sibling module outputs within that same session, but when running only one module in another session, Maven may have to look up sibling artifacts in a local/remote repository.

## 6. `-pl`: Selecting Projects by Path or Coordinates

`-pl` is short for `--projects` and specifies the subset of projects to build in the reactor. Equivalent ways to select the demo app (from root):

```bash
# Select by relative directory name:
mvn -pl boot-app package

# Select by artifactId (leading colon):
mvn -pl :boot-app package

# Select by groupId:artifactId:
mvn -pl com.example:boot-app package

# Select multiple modules separated by commas:
mvn -pl :core-lib,:boot-app package
```

In Maven 3:
- `-pl boot-app` matches the module's **path**.
- `-pl :boot-app` matches the **artifactId**.
- `-pl com.example:boot-app` matches **groupId:artifactId**.
- If the directory name differs from the `artifactId`, choose the matching format; do not assume the two names are identical.
- `-pl` selects only Maven projects **already in the reactor**; it does not search Maven Central for arbitrary artifacts of the same name.

### 6.1. Why Can Using `-pl` Alone Fail?

Run:

```bash
mvn -B -ntp -pl :boot-app package
```

Maven is told to build `boot-app`, **not** to build upstream `service-lib` and `core-lib`. On a clean machine, an uninstalled/unpublished sibling `0.0.1-SNAPSHOT` can cause dependency resolution to fail. On a dev machine where an older version of `service-lib` was previously installed, the command might "PASS" while running against an **outdated JAR** instead of the current repository source.

Therefore, `-pl` alone is suitable when a module has no sibling dependencies, or when you **intentionally** consume already published/installed binaries in a controlled manner. In an active monorepo, if you want to build sibling dependencies from source, add `-am`.

### 6.2. Module Path, Selector, and Root POM

If a module lives in `apps/payments/` while its `artifactId` is `checkout-api`, selectors are:
- `-pl apps/payments`: by path.
- `-pl :checkout-api`: by artifactId.
- `-pl com.example:checkout-api`: by short GAV.

If you invoke Maven from a directory outside the root, you can specify the POM file:

```bash
mvn -f /path/to/reactor-demo/pom.xml -pl :boot-app -am package
```

`/path/to/reactor-demo` is an illustrative path. When debugging selection, the simplest approach is to `cd` into the root containing the aggregator `pom.xml` and run reactor commands there.

## 7. `-am`: Automatically Selecting Prerequisites in the Same Reactor

`-am`/`--also-make` adds the reactor projects that the selected projects depend on. For the demo:

```bash
mvn -B -ntp -pl :boot-app -am clean package
```

In terms of relationships:

```text
             selected by -pl
                  |
                  v
core-lib ---> service-lib ---> boot-app
    ^              ^
    |              |
    +------ -am finds upstream prerequisites
```

The resulting build set includes the app and its relevant upstream siblings (along with any required parent POM). If another module has no dependency edge to the app, it is generally **not** pulled into the closure just for appearing in root `<modules>`.

**`-am` does not build source code of external dependencies** like Spring MVC, Jackson, Hibernate, or Tomcat. Artifacts outside the reactor are still resolved by Maven from local/remote repositories according to the POM and settings.

### 7.1. Comparing Selection Commands and Closures

| Command from Root | Expected Work Set | Meaning |
| --- | --- | --- |
| `mvn package` | All modules | Full reactor build |
| `mvn -pl :boot-app package` | Boot app | May miss sibling artifacts on a clean machine |
| `mvn -pl :boot-app -am package` | App + service + core + required parent | Selects upstream prerequisites |
| `mvn -pl :service-lib -am package` | Service + core + required parent | Does not automatically test `boot-app` |
| `mvn -pl :core-lib -am package` | Core + required parent | Does not automatically build downstream consumers |
| `mvn -pl :core-lib,:boot-app -am package` | Union of upstream closures for both | Shared required modules build only once |

The table describes **the demo's module relationships**, not a promise of exact log line counts, because Maven versions and parent/plugin relationships can affect which projects execute.

### 7.2. `-am` Does Not Invent Missing Dependencies

If `service-lib` Java code imports `GreetingFormatter` yet its POM omits `core-lib` from `<dependencies>`, the reactor cannot infer the edge by scanning Java `import` statements. Nor can `-am` fix a POM missing a dependency. You must declare the correct `groupId`/`artifactId`/`version`/`scope` and inspect the dependency tree.

If `core-lib` lives outside the reactor (for instance, an artifact from another repository), `-am` does not automatically "clone" its source repository or hunt for sibling modules outside the aggregator; Maven resolves the binary normally.

## 8. `-amd`: Selecting Modules That Depend on a Modified Module

`-amd`/`--also-make-dependents` goes **downstream**. When changing a core API, you want to see if the service and app still compile:

```bash
mvn -B -ntp -pl :core-lib -amd verify
```

For the demo, consider the relationships:

```text
selected:
  core-lib ---> service-lib ---> boot-app
               dependents of core
```

`-am` and `-amd` are opposites:
- `-am` adds modules **used by the selected modules**.
- `-amd` adds modules **that use the selected modules**.
- `-pl` defines the starting point.
- When needing both directions in a large repo, inspect the actual build set rather than assuming every branch is included.

**Note for clean environments:** `-amd` does not automatically add every other prerequisite of each downstream project the way `-am` does; parents/build extensions or other upstreams may need to be built alongside it. For CI release gates, a full `mvn clean verify` is usually the most reliable baseline, while partial selection is an optimization to measure.

### 8.1. When to Use `-amd`?

Suppose you change a public method signature in `GreetingFormatter`. Testing `core-lib` alone can PASS while `service-lib` and `boot-app` fail to compile. Running `-amd verify` reveals the impact on consumers. Conversely, when you only want to run the web app after editing a shared module, `-pl :boot-app -am` is the more natural path.

## 9. `-rf`/`--resume-from`: Continuing After a Failed Build

Maven 3 can print a resume suggestion after a module fails:

```bash
mvn -rf :service-lib package
```

`-rf` typically skips projects appearing earlier than the resume point in reactor order and runs the rest. However, it **does not automatically rebuild upstream dependencies**.

Example from a previous build:

```text
Reactor Demo Parent    SUCCESS
core-lib               SUCCESS
service-lib            FAILURE
boot-app               SKIPPED
```

After fixing `service-lib`:
- If upstream artifacts were already installed/published at the right version and unchanged, resuming can save time.
- If the previous build only ran `package`, `core-lib` may only have a JAR in `core-lib/target`, **not yet in the local Maven repository**. When resuming skips core, Maven may fail again trying to resolve `core-lib`.
- Safe command when unsure of machine state: `mvn -pl :boot-app -am package` or full `mvn clean verify`.

`-rf` does not mean "resume at the exact test instruction where it stopped"; lifecycles/goals re-run for the selected projects. With Maven 4, selection/resume semantics change further; do not copy commands mechanically when upgrading Maven major versions.

## 10. `-T`: Parallelizing Without Breaking Dependency Order

Maven supports a parallel reactor:

```bash
mvn -B -ntp -T 1C clean verify
```

`-T 1C` tells Maven to use a thread count proportional to CPU cores; you can also pass `-T 4` to specify an exact thread count. However:

- `core-lib → service-lib → boot-app` is a linear dependency chain and cannot run all three modules simultaneously.
- In a branching graph, such as core → audit-lib and core → reporting-lib, the two independent modules can run in parallel once core is ready.
- Non-thread-safe plugins or tests sharing ports, databases/schemas, or temp folders can cause flaky failures.
- Logs across modules can interleave due to parallelism; do not infer ordering bugs merely from adjacent console lines.
- CI should verify Maven plugin compatibility and isolate test resources before increasing `-T`.

`-T` is a **scheduling** optimization; it does not replace `<dependency>` and does not cure cyclic dependencies.

## 11. Fail Fast, Fail at End, and Non-Recursive Builds

| Flag | Primary Behavior | Notes |
| --- | --- | --- |
| `-ff`/`--fail-fast` | Stops early when a module fails; typically the default | Good for fast feedback |
| `-fae`/`--fail-at-end` | Continues modules that do not depend on the failed part, reports failure afterward | Useful for collecting multiple failures |
| `-fn`/`--fail-never` | Suppresses normal failure exit status | **Avoid using as a CI release gate** |
| `-N`/`--non-recursive` | Does not descend into child modules | Builds only the current project |

Examples:

```bash
mvn -B -ntp -fae clean verify
mvn -N validate
```

When `core-lib` fails, modules depending on core cannot build successfully due to missing required classes; `-fae` allows an **independent** branch to proceed without forcing Maven to ignore dependency edges.

`mvn -N validate` runs on the working directory's project (the aggregator at root) and **does not** automatically build all modules. `-N` is not a way to select an arbitrary sibling module.

## 12. `dependencyManagement` and `pluginManagement` Do Not Create Reactor Edges

Example in the root parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The block above **only manages versions** if a child later declares an actual dependency. For `service-lib` to actually use core:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core-lib</artifactId>
    </dependency>
</dependencies>
```

Only when both blocks are present does the edge `core-lib → service-lib` form. With `dependencyManagement` alone, the reactor does not build core before service simply because "the project mentions core's name" in management.

Similarly:
- `pluginManagement` defines Maven plugin versions/default config **if a project actually uses the plugin**.
- `build/plugins` declares plugins actively used in a module, which can create a reactor relationship when the plugin itself is a reactor module.
- `modules` collects POMs; it does not force Maven to add classpath dependencies.
- The Spring Boot BOM manages dependency versions; it is not an ordering tool for local sibling modules.

This is why a root POM can look like it lists every version yet the reactor still fails: consuming modules have not declared real edges.

## 13. Spring Boot Maven Plugin: Avoid Repackaging Every Library Module

In a Spring Boot multi-module setup:
- `core-lib` and `service-lib` are **plain JARs**; classes sit at the root by Java package, suitable as dependencies.
- `boot-app` is an **executable JAR**; the loader places application classes under `BOOT-INF/classes` and dependencies under `BOOT-INF/lib`.

If you put `spring-boot-maven-plugin` in root `<build><plugins>` and let children inherit it, `repackage` can run on libraries, causing missing-main-class errors or turning archives into executable layouts unsuitable for consumers expecting normal Maven JARs.

Example configuration that **should not leak to libraries**:

```xml
<!-- Do not put this plugin in parent build/plugins if all libraries inherit from it -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
```

This is a **plugin snippet**, not a complete POM. Only `boot-app` needs the plugin as shown in section 4.5. The parent can manage its version in `pluginManagement`; the child app declares the plugin in `build/plugins` to activate it.

Within the app module, the `package` lifecycle typically runs `maven-jar-plugin:jar` first, followed by `spring-boot-maven-plugin:repackage`. Reactor dependencies order **modules**, whereas repackaging is a goal **inside the application module**; these two levels of ordering must not be confused.

## 14. Optimizing CI/CD Without Relying on Accidental Caching

### 14.1. Full Reactor Build as Baseline

A trustworthy pipeline should include a step:

```bash
mvn -B -ntp clean verify
```

It checks all modules in the reactor in valid order. Only afterward should you measure timings and adopt partial builds.

### 14.2. Partial App Build with `-pl` and `-am`

For a job needing only the executable Spring Boot JAR:

```bash
mvn -B -ntp -pl :boot-app -am clean verify
```

This command builds the app along with local prerequisites known to Maven via the dependency graph. Avoid "manually install core, manually install service, then package app" because manual sequencing easily misses changes and causes local Maven repository drift across branches.

If the repository has a wrapper, use it instead of the global Maven CLI:

```bash
./mvnw -B -ntp -pl :boot-app -am clean verify
```

On Windows use `mvnw.cmd`. Use the exact Java/Maven versions tested in CI.

### 14.3. Downstream Testing When Changing Shared Code

If a pull request modifies only `core-lib`, do not run just `mvn -pl :core-lib -am verify` and assume consumers are safe. You need a job testing dependent modules, for example:

```bash
mvn -B -ntp -pl :core-lib -amd verify
```

In a large reactor, downstream modules may require other prerequisites outside the selection; compute the appropriate closure, or fall back to a full build for release gates. Flags are **graph selection** tools, not a replacement for CI coverage strategy.

### 14.4. Distinguishing `package`, `install`, and `deploy`

- `package`: creates JAR/WAR artifacts in each project's `target` directory.
- `verify`: runs up to the verify phase, which may include integration/quality goals if configured.
- `install`: installs artifacts into the **local** Maven repository for use by other Maven invocations.
- `deploy`: publishes to a **remote** Maven artifact repository, requiring `distributionManagement`/credentials.

Reactor builds in a single invocation usually do not need `install` between modules to resolve sibling artifacts. Use `install` only when genuinely required; do not turn the local cache into a "source of truth" for current source code.

### 14.5. Be Careful with SNAPSHOTs and Caches

When multiple branches share the coordinate `com.example:core-lib:0.0.1-SNAPSHOT`, running `mvn install` into a shared local repository can cause another branch's build to pick up the wrong binary.

Better workflow:
- Use the reactor's selected closure within a single Maven invocation.
- Keep CI workspace/cache boundaries clean; isolate the local repository per job if necessary.
- Pin build/plugin versions and log Maven/JDK versions.
- When publishing, use traceable version/commit metadata and standard repository mechanisms rather than relying on one generic SNAPSHOT name.
- Verify the exact artifact `boot-app/target/boot-app-0.0.1-SNAPSHOT.jar` and run a smoke test.

## 15. Diagnostic Commands When a Reactor Build Fails

```bash
mvn -version
mvn -B -ntp clean verify
mvn -B -ntp -pl :boot-app -am package
mvn -B -ntp -pl :boot-app dependency:tree
mvn help:effective-pom
```

**Note:** `dependency:tree` is a goal of the Maven Dependency Plugin and may require plugin resolution from a repository. `help:effective-pom` is a goal of the Maven Help Plugin, useful for inspecting inherited parent, `dependencyManagement`, and plugin executions. When sibling source artifacts are not yet available in the selected reactor or local cache, running certain goals on a single module alone can fail resolution. Check your CLI flags, reactor selection, and dependency graph first.

Do not use `-q`/`--quiet` when trying to inspect `Reactor Build Order` and `Reactor Summary`, because quiet mode can hide information needed for debugging.

### 15.1. Fault-Isolation Procedure

1. Stand at the aggregator root and confirm `<modules>` points to the right child directories.
2. Check Maven/JDK versions, parent POM, and children's `relativePath`.
3. Confirm consuming modules have an **actual dependency** on the sibling artifact with matching `groupId`/`artifactId`/`version`.
4. Run a full build to observe the reactor order and the first failing module.
5. Try `-pl :boot-app -am package` to verify the upstream closure.
6. If **sibling artifact resolution** fails, check for missing `-am`, mismatched coordinates, or stale local repository artifacts.
7. If **external artifact resolution** fails, check Maven repositories/mirrors/proxies/credentials; `-am` cannot fix network errors.
8. If **compile/test** fails, fix source/test/plugin config; the reactor only handles ordering.
9. If **Spring Boot packaging** fails, confirm the Boot plugin is only on the app, along with the main class and archive layout.
10. If a failure happens after `-rf`, rerun the upstream closure instead of relying on artifacts sitting only in `target`.
11. If intermittent failures occur with `-T`, temporarily run sequentially and check thread safety or shared resources.

## 16. Common Errors and Fixes

| Symptom | Likely Cause | Solution |
| --- | --- | --- |
| `Could not find artifact com.example:service-lib` | Selected `boot-app` with `-pl` without upstreams | Add `-am` from the root reactor |
| Maven finds an old `core-lib` in cache | Sibling was not built in this invocation; overlapping SNAPSHOT version | Run the selected closure; align versions/cache isolation |
| `package ... does not exist` in consumer module | Missing `<dependency>`, wrong scope, or wrong version | Add an actual dependency, not just `dependencyManagement` |
| Build order differs from `<modules>` order | Reactor topologically sorts dependencies | This is correct behavior; review reactor sort rules |
| Maven does not recognize `-pl :module` | Different `artifactId`, module outside reactor, or wrong root | Check aggregator POM and exact selector |
| Parent POM fails to resolve | Wrong `relativePath`/GAV or unavailable parent | Fix parent coordinates, `../pom.xml` |
| Reactor reports cyclic reference | Two modules depend on each other in a loop | Extract interfaces/models, refactor graph |
| App module does not create an executable JAR | Boot Maven plugin not declared in app | Declare plugin and ensure `repackage` execution |
| Library module reports missing main class | Boot plugin inherited by library | Enable plugin only in app |
| Consumer cannot read classes from executable JAR | Boot JAR layout is not a plain Java library | Keep library modules as plain JARs |
| `-rf` fails despite upstream SUCCESS previously | Upstream was packaged but not installed; resume skipped upstream | Re-run `-pl ... -am` or full reactor |
| `-amd` does not select expected downstreams | Missing dependency edge or module outside reactor | Fix dependency/aggregation, inspect graph |
| `-T` causes flaky failures | Non-thread-safe plugin/tests, shared state | Run sequentially, isolate resources |
| CI passes despite test failures | Used `-fn`, ignored exit code, skipped tests | Remove `-fn`, check status and test reports |
| Build fails only on CI | Maven/JDK/repo/cache/root differs from dev | Use wrapper, log versions and CI settings |
| `curl` to app fails | JAR/app not started, different port, or bootstrap error | Check Spring logs, port, and right artifact |

## 17. Reactor Flags Quick Reference

| Flag | Long Form | Effect |
| --- | --- | --- |
| `-pl` | `--projects` | Select starting module(s) |
| `-am` | `--also-make` | Also build **upstream** prerequisites |
| `-amd` | `--also-make-dependents` | Also build **downstream** consumers |
| `-rf` | `--resume-from` | Resume from a project in reactor order |
| `-N` | `--non-recursive` | Do not descend into child modules |
| `-T` | `--threads` | Allow parallel reactor when safe |
| `-ff` | `--fail-fast` | Stop when a module fails |
| `-fae` | `--fail-at-end` | Continue independent branches, fail at end |
| `-fn` | `--fail-never` | Do not use for release gates |
| `-f` | `--file` | Select input POM, such as root POM |

Summary: **`-pl` selects target modules; `-am` adds what the targets need; `-amd` adds what needs the targets**. Maven still sorts the selected projects according to declared dependency edges.

## 18. Study Resources and Final Checklist

### Checklist

- Root `pom.xml` has `pom` packaging and lists modules with valid paths.
- Child modules use a parent with accurate `groupId`/`artifactId`/`version`, and `relativePath` when appropriate.
- Java relationships between siblings are declared in `<dependencies>`.
- No circular dependencies or duplicate module coordinates exist.
- `dependencyManagement`/`pluginManagement` are not mistaken for actual dependency edges.
- Library modules are plain JARs; the Spring Boot executable plugin lives only in the app module.
- Full reactor build passes before optimizing with selective CI builds.
- When building the app from monorepo source, use `-pl :boot-app -am` to include upstream prerequisites.
- When changing a core public API, check downstreams via `-amd`/full build.
- Do not rely on `-rf` to rebuild uninstalled upstreams; avoid stale local binary caches.
- Enable `-T` only when plugins/tests are safe to run in parallel.
- Reactor summary and exit status are genuinely checked; `-fn` is never used for deploy decisions.
- CI checks the right executable JAR, Java runtime, smoke test, and artifact checksum.

### Official Documentation

- Apache Maven 3 – [Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): collection, reactor sorting, and selectors.
- Apache Maven – [POM Reference](https://maven.apache.org/pom.html): aggregation, inheritance, `<modules>`, `<dependencies>`, `dependencyManagement`.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package/verify/install/deploy.
- Apache Maven 3.9.9 – [CLI Options](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): `-pl`, `-am`, `-amd`, `-rf`, `-T`, and failure modes.
- Apache Maven 4 – [Working with Multiple Subprojects](https://maven.apache.org/guides/mini/guide-multiple-subprojects-4.html): differences when using Maven 4.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JARs and the `repackage` goal.
- Spring Boot 3.5 – [Using the Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent and plugin configuration.

**Conclusion:** The Maven reactor collects multi-module projects, sorts them according to **actually used** dependencies, and builds selected projects in a valid order. `-pl` narrows down modules; `-am` pulls in same-reactor prerequisites to avoid stale local artifacts; `-amd` verifies downstream impact on consumers. In multi-module Spring Boot applications, keep library modules as plain JARs, build an executable JAR only for the application module, and use `mvn -pl :boot-app -am clean package` whenever you need to build the application along with its entire library chain.