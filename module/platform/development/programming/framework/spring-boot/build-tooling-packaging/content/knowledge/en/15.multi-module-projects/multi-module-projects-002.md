# Distinguishing Maven Parent, Aggregator, and Inter-Module Dependencies in Spring Boot

## 1. The Problem: Being in the Same Repository Does Not Mean the Same Relationship

A large Spring Boot project can be split into `domain` (shared models/business logic), `web-app` (HTTP application), `batch` (background processing), and several integration libraries. Maven supports organizing them with **multiple projects/POMs**, but there are **three completely different types of relationships** to distinguish:

1. **Parent / inheritance**: a child POM has `<parent>` pointing to a parent POM to **inherit configuration** such as default group/version, properties, `dependencyManagement`, and `pluginManagement`.
2. **Aggregator / aggregation**: a POM has `<modules>` listing module paths so Maven **gathers and builds them in one reactor**. The reactor orders projects according to actual build relationships.
3. **Inter-module dependency**: project A declares `<dependencies><dependency>...B...</dependency></dependencies>` to **use module B's artifact and classes** on the appropriate classpath.

These three relationships may exist together, or exist independently.

| Relationship | Where Is It Declared? | Primary Function | Does It Automatically Put Another Module's Classes on the Classpath? |
|---|---|---|---|
| Parent | **Child** POM: `<parent>` | Inherits build configuration | **No**, not merely by being a parent |
| Aggregator | **Aggregating** POM: `<modules>` | Selects which projects participate in the reactor | **No**, not merely by being in the same modules list |
| Dependency | **Consuming module** POM: `<dependencies>` | Represents artifact usage; determines classpath and build order | **Yes**, when scope and artifact are appropriate |
| Dependency management | Managing POM: `<dependencyManagement>` | Manages versions/scopes for dependencies **if declared/used** | **No**, does not add dependencies automatically |
| Plugin management | Parent/POM: `<pluginManagement>` | Manages default versions/configuration for plugins | **No**, does not apply every plugin/task automatically |

**Rule of thumb:** `<parent>` asks **"who do I inherit from?"**; `<modules>` asks **"who gets built together?"**; `<dependencies>` asks **"whose code do I use?"**. These questions cannot substitute for one another.

## 2. Geometric Model: Three Kinds of Edges in One Project

Example repository:

```text
acme-platform/
├── pom.xml                     (parent + aggregator)
├── domain/
│   ├── pom.xml                 (library)
│   └── src/main/java/...
└── web-app/
    ├── pom.xml                 (Spring Boot application)
    └── src/main/java/...
```

You can draw **three independent diagrams**:

```text
INHERITANCE (<parent> relationship)
       acme-platform
          /    \
       domain  web-app

AGGREGATION (<modules> relationship)
  acme-platform reactor
       +-- domain
       +-- web-app

DEPENDENCY (<dependency> relationship)
  web-app ----------> domain
  [uses class Greeter from domain]
```

In the example above, the root POM is **both** parent **and** aggregator, yet that **does not automatically create** a dependency arrow from `web-app` to `domain`. The final arrow only appears if the `web-app` POM declares a dependency on the `domain` artifact.

**Distinguish build order from the dependency graph:** The reactor can build `domain` before `web-app` because it detects this module dependency. It does **not** require you to place `domain` first in the `<modules>` list as long as the dependency relationship is properly declared.

## 3. Parent POM: Configuration Inheritance, Not a Module-Grouping Mechanism

### 3.1. How to Declare a Parent?

In `domain/pom.xml`:

```xml
<parent>
    <groupId>com.example.acme</groupId>
    <artifactId>acme-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
```

Maven looks up the parent POM with coordinates `com.example.acme:acme-platform:1.0.0-SNAPSHOT`. `<relativePath>../pom.xml</relativePath>` is the path **from the directory containing the child POM** to the parent POM file in the source checkout. If `relativePath` is omitted, Maven checks `../pom.xml` by default; writing it explicitly in examples makes the intent clear.

When the **parent is an external artifact** that is already published, such as the Spring Boot starter parent, `<relativePath/>` is commonly used so Maven does not try to infer a parent POM in the parent directory of the current repository:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
```

The two snippets above describe **two different levels**: the root `acme-platform` can inherit `spring-boot-starter-parent`; child modules inherit `acme-platform`. A Maven POM declares only **one direct `<parent>`**, but configuration can be inherited through a **multi-level parent chain**.

### 3.2. What Does a Parent Inherit/Provide?

Depending on the POM and the Maven model, elements that can be inherited/merged include:

- Project `groupId` and `version` if not overridden by the child.
- `properties` such as `java.version` and `project.build.sourceEncoding`.
- `dependencyManagement` and `pluginManagement`.
- Certain `dependencies` and plugin/execution configurations placed in the parent's directly applied sections.
- Build configuration, repositories, and reporting according to Maven's inheritance rules.

**Not every part of the parent is copied verbatim.** Child POMs have their own `artifactId` and can override many properties; `<modules>` in a parent is the aggregator's module list, **not an automatically generated module list in every child POM**.

Run `./mvnw -pl :web-app help:effective-pom` to inspect the effective configuration merged from the Super POM, Spring Boot parent, root parent, and child POM. If your machine does not have Maven Wrapper, use `mvn` matching your organization's standardized version.

### 3.3. Why Do Parents Usually Have packaging=pom?

A parent holds metadata/configuration rather than compiling a specific Java library, so it usually declares:

```xml
<packaging>pom</packaging>
```

A parent POM can be `install`ed or `deploy`ed as a **POM artifact** so child projects in other repositories can still resolve the parent configuration. It **does not** generate Java classes for a child module simply by sitting in the same directory tree.

In the multi-module example, the root POM has `packaging=pom`, while `domain` and `web-app` have `jar` packaging. Child modules do not inherit `pom` packaging as their primary archive type: set the right packaging for each module's role when needed, and keep in mind that Maven's default packaging is `jar`.

### 3.4. Pitfall: dependencies in a Parent vs dependencyManagement

If the root parent puts:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

then this declaration can be **inherited by child POMs** as an actual dependency. As a result, `domain`, despite being a plain Java library, can also receive the web starter on its classpath — which is usually undesirable.

If you only want shared version management, put the dependency in `<dependencyManagement>`; when a module actually needs to use it, **each module declares it** in `<dependencies>`. Likewise, the Spring Boot plugin for creating executable archives should not be applied broadly to library modules just because the parent manages the plugin version.

## 4. Aggregator POM and Maven Reactor: Grouping Projects to Build

### 4.1. Declaring Modules by Path

In the root `pom.xml`:

```xml
<packaging>pom</packaging>
<modules>
    <module>domain</module>
    <module>web-app</module>
</modules>
```

`<module>domain</module>` is a **relative path to a project in the repository**, not a `groupId:artifactId:version` GAV. It often matches the `artifactId` for readability, but Maven cares about the POM path, so the directory name can differ from the `artifactId`.

When running from the root:

```bash
./mvnw clean verify
```

The Maven reactor collects the root project and declared modules, computes the proper order, and runs goals/phases on the selected projects. You do not need to manually run `cd domain && mvn install` before `cd web-app && mvn package` for a properly configured reactor build.

**Reactor is not the same as a repository:** The reactor operates on projects within a single Maven invocation; the Maven local repository (`~/.m2/repository`) stores cached/installed artifacts. Within a reactor, a dependency matching a module in the same build session can be resolved from the reactor build without requiring every module to be installed first.

### 4.2. Reactor Order Depends on "Actually Declared" Relationships

The Maven reactor examines relationships such as:

- Module A has an **actual dependency** on module B in the same reactor.
- Module A uses another module as a plugin/build extension or plugin dependency where applicable.
- A project uses a parent located in the reactor.
- The `<modules>` order acts only as a **tiebreaker** when no stronger relationship determines precedence.

Important: `<dependencyManagement>` or `<pluginManagement>` entries **do not** make the reactor order modules as if an actual dependency/plugin existed. For instance, if the root manages the version of `domain` but `web-app` does not declare a `<dependency>` on `domain`, Maven will not automatically infer that `web-app` needs `domain`'s classes.

### 4.3. Aggregator and Parent Can Be Two Different Projects

A repository can use:

```text
repo/
├── build-all/pom.xml      (aggregator: declares <modules>)
├── shared-parent/pom.xml  (parent: shared standard, publishable)
├── domain/pom.xml         (parent = shared-parent)
└── web-app/pom.xml        (parent = shared-parent;
                           dependency = domain)
```

`build-all` can list `../domain` and `../web-app` in `<modules>`, while `domain` and `web-app` inherit `shared-parent` and **do not inherit build-all**. This design suits organizations that reuse a corporate parent across multiple repositories while still grouping several modules into a reactor.

Conversely, a POM in an internal repository can serve as the **parent** for many projects **without having `<modules>`**. It remains a valid parent because inheritance does not require aggregation.

## 5. Inter-Module Dependency: What Actually Puts Shared Code on the Classpath?

Suppose the class `com.example.acme.domain.Greeter` lives in the artifact:

```text
com.example.acme:domain:1.0.0-SNAPSHOT
```

In `web-app/pom.xml`, you must declare:

```xml
<dependencies>
    <dependency>
        <groupId>com.example.acme</groupId>
        <artifactId>domain</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

This is a **direct** dependency, creating a compile/runtime relationship via the default `compile` scope. If `web-app` source calls `Greeter` while only `<module>domain</module>` exists in the aggregator, Maven will not put `domain.jar` onto the classpath and the compiler may report `package com.example.acme.domain does not exist`.

One module **depends** on another through artifact version and GAV; sharing the same `<parent>` does not create a classpath relationship.

### 5.1. dependencyManagement Only Manages Versions

If the root parent has:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example.acme</groupId>
            <artifactId>domain</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

then `web-app` can declare a versionless dependency:

```xml
<dependency>
    <groupId>com.example.acme</groupId>
    <artifactId>domain</artifactId>
</dependency>
```

**However, there must still be a dependency declaration in `web-app`.** Merely putting `domain` inside `dependencyManagement` does not make `Greeter` appear on the runtime classpath. When modules use different versions or release independently, `${project.version}` is not a safe default; dependency versions must be managed explicitly according to your actual release policy.

### 5.2. Scopes and Transitive Dependencies

| Maven Scope | Common Meaning in a Dependent Module |
|---|---|
| `compile` (default) | Used at compile and runtime; can propagate transitively to consumers |
| `runtime` | Needed at runtime, usually not needed directly at compile time |
| `provided` | Needed for compile/test, expected to be supplied by an external runtime/container; not the usual way to declare a shared internal module |
| `test` | Only for that module's tests; does not become a main dependency for another application |
| `import` | Valid only when importing a POM into `dependencyManagement` with `type=pom`; **not** a runtime dependency |

For example, when `web-app` depends on `domain` in `compile` scope, `domain`'s public APIs should be kept stable if other modules consume them. A module's own test-only dependencies **do not leak** into `web-app`'s runtime simply because `web-app` depends on that module.

To inspect actual resolved dependencies, run `dependency:tree` on the specific module; do not rely solely on root `<modules>` or `dependencyManagement`.

## 6. Complete Java 17 + Spring Boot 3.5 Example: Root as Both Parent and Aggregator

This section builds a **Maven-buildable** repository consisting of a Java library module and a Spring Boot web application module. Each file has an explicit name and content; alternative configurations shown in later sections are **variants**, not additions to be pasted on top of this POM.

### 6.1. Directory Tree

```text
acme-platform/
├── pom.xml
├── mvnw, mvnw.cmd, .mvn/wrapper/...    # Maven Wrapper (from Initializr or generated separately)
├── domain/
│   ├── pom.xml
│   └── src/
│       └── main/java/com/example/acme/domain/
│           └── Greeter.java
└── web-app/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/acme/app/
        │   ├── WebApplication.java
        │   └── GreetingController.java
        └── test/java/com/example/acme/app/
            └── GreetingControllerTest.java
```

For a manually created project without a Maven Wrapper yet, you can use a suitable installed `mvn`; for team/CI work, **properly generate and commit the Maven Wrapper** rather than creating dummy script files. The commands below assume the wrapper is present.

### 6.2. Root pom.xml — Parent + Aggregator

`acme-platform/pom.xml` is the **complete POM**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.acme</groupId>
    <artifactId>acme-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>web-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.acme</groupId>
                <artifactId>domain</artifactId>
                <version>${project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Explanation of the layers:

- The root inherits Spring Boot's `spring-boot-starter-parent` for Java/plugin/dependency management defaults.
- The root is the **parent of the repository's modules** via the `<parent>` section in each child POM (see sections 6.3 and 6.5).
- The root is the **aggregator** via `<packaging>pom</packaging>` and `<modules>`.
- The root **manages the version** of the `domain` module via `dependencyManagement`, yet **does not automatically add `domain` to `web-app`'s classpath**.
- The root **does not** directly apply `spring-boot-maven-plugin` to build an executable JAR for `domain`; the plugin is placed specifically in the application module.

Because all modules in the example inherit version `1.0.0-SNAPSHOT`, `${project.version}` works for managing `domain`'s version. If a project chooses multiple release streams/separate versions, adjust the version management strategy.

### 6.3. domain/pom.xml — Plain Java Library

`domain/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.acme</groupId>
        <artifactId>acme-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>domain</artifactId>
    <packaging>jar</packaging>
</project>
```

This module inherits group/version/Java configuration and dependency management, yet **does not need** the Spring Boot Maven Plugin or `spring-boot-starter-web`. Its main output is the ordinary Java library `domain-1.0.0-SNAPSHOT.jar`, ready for other modules to use on the classpath.

### 6.4. Greeter.java — Pure Java 17 Code

`domain/src/main/java/com/example/acme/domain/Greeter.java`:

```java
package com.example.acme.domain;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

This class does not use Spring Framework. It is packaged into the `domain` artifact and used by the web application via a Maven dependency. Having the Java package `com.example.acme.domain` does not cause Maven to automatically recognize a dependency; **dependencies are relationships between artifacts, not between Java package names**.

### 6.5. web-app/pom.xml — Boot Application Depending on domain

`web-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.acme</groupId>
        <artifactId>acme-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>web-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example.acme</groupId>
            <artifactId>domain</artifactId>
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

**The crux lies in two separate places:**

- `<dependency>domain</dependency>` in `web-app` creates the usage relationship for `domain.jar`. Its version is drawn from the root's `dependencyManagement`.
- `spring-boot-maven-plugin` is **applied only** in `web-app` to produce an executable JAR; the Spring Boot parent already manages the version/configuration and appropriate repackage goal.

`web-app` does not need to repeat the version of `spring-boot-starter-web` because the version is managed along the chain `spring-boot-starter-parent` → `acme-platform` → `web-app`.

### 6.6. WebApplication.java — Main Class and Bean Registration from domain

`web-app/src/main/java/com/example/acme/app/WebApplication.java`:

```java
package com.example.acme.app;

import com.example.acme.domain.Greeter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @Bean
    public Greeter greeter() {
        return new Greeter();
    }
}
```

`Greeter` lives in another module and in package `com.example.acme.domain`. We register `@Bean` explicitly so Spring can inject it; **a Maven dependency only places classes on the classpath** and does not automatically turn every plain Java class into a Spring bean. If you use component scanning and annotations, design scan boundaries intentionally rather than guessing that `@SpringBootApplication` will scan every package of every module.

### 6.7. GreetingController.java — Using a Class from the domain Module

`web-app/src/main/java/com/example/acme/app/GreetingController.java`:

```java
package com.example.acme.app;

import com.example.acme.domain.Greeter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final Greeter greeter;

    public GreetingController(Greeter greeter) {
        this.greeter = greeter;
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "Java") String name) {
        return greeter.greet(name);
    }
}
```

`@RequestParam` specifies `name` explicitly so the example does not rely on parameter name reflection. Constructor injection proves `Greeter` is registered as a Spring bean; the `Greeter` class compiles only because **Maven has an actual dependency from `web-app` to `domain`**.

### 6.8. GreetingControllerTest.java — Verifying the web-app Module

`web-app/src/test/java/com/example/acme/app/GreetingControllerTest.java`:

```java
package com.example.acme.app;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void defaultsToJava() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Java"));
    }

    @Test
    void passesQueryToDomain() throws Exception {
        mockMvc.perform(get("/hello").param("name", "Maven"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Maven"));
    }
}
```

This is a test inside a Maven project with `spring-boot-starter-test`; it requires the Maven/JUnit/Spring classpath and is **not** a standalone `javac` file. The test uses MockMvc and does not open HTTP port 8080. If it fails, read the stacktrace to distinguish compile/dependency errors, context/bean errors, and assertion failures.

## 7. Build Commands and Self-Check Results

### 7.1. Build the Whole Reactor from Root

At the `acme-platform/` root, run:

```bash
./mvnw clean verify
```

Maven includes the root POM, `domain`, and `web-app` in the reactor. The logical order is the root parent first, then `domain` before `web-app` because `web-app` **depends on** `domain`. Even if you reverse the two `<module>` entries in the root POM, the declared dependency still determines the required order.

When the build succeeds, the artifacts normally produced are:

```text
domain/target/domain-1.0.0-SNAPSHOT.jar
web-app/target/web-app-1.0.0-SNAPSHOT.jar
```

`domain` is an ordinary Java library JAR; `web-app` is a Spring Boot executable JAR because only this module applies the Spring Boot Maven Plugin. Filenames assume `finalName` or classifiers have not been changed.

### 7.2. Run the Executable JAR After Building

```bash
java -jar web-app/target/web-app-1.0.0-SNAPSHOT.jar
```

In another terminal, call:

```bash
curl -s "http://localhost:8080/hello"
curl -s "http://localhost:8080/hello?name=Maven"
```

The **response bodies** are respectively:

```text
Hello, Java
Hello, Maven
```

This is not the complete application startup stdout; Spring Boot also prints startup logs. If port 8080 is already in use, pass `--server.port=8081` after the JAR name and call the URL with port 8081.

### 7.3. Build Only the Application Module and What It Needs

```bash
./mvnw -pl :web-app -am verify
```

Where:

- `-pl :web-app` (`--projects`) selects the project with `artifactId=web-app` in the reactor.
- `-am` (`--also-make`) **additionally selects projects that `web-app` needs**, such as `domain` and the parent in the same reactor when applicable.
- `verify` runs the lifecycle up to the verify phase for the selected projects.

On a clean checkout, running:

```bash
./mvnw -pl :web-app verify
```

**can fail** because the internal `domain` dependency has not been built/installed/made available in the repository. `-pl` alone selects a project and **does not mean** Maven automatically builds all dependencies in the reactor. When developing modules together, `-pl ... -am` is usually the appropriate choice.

### 7.4. Inspect Build Order and Dependency Graph

```bash
# Inspect the dependency tree of the web-app module
./mvnw -pl :web-app dependency:tree

# View the effective POM after inheritance
./mvnw -pl :web-app help:effective-pom

# Build only the library and required parents
./mvnw -pl :domain -am verify
```

In `web-app`'s dependency tree, you should see `com.example.acme:domain:jar:1.0.0-SNAPSHOT` (in addition to Spring Boot dependencies) when dependencies are resolved. If the project has not yet built/installed the domain artifact, running the dependency plugin alone may require a reactor build first, such as `./mvnw -pl :web-app -am verify`.

## 8. Standalone Java Standard Library Example to Verify `domain` Before Maven

`Greeter.java` is plain Java. You can verify this class directly without Spring, helping separate "does the library code work" from "is the Maven dependency declared properly".

Create an extra **test file outside Maven source sets**, `examples/GreeterProbe.java`:

```java
import com.example.acme.domain.Greeter;

public class GreeterProbe {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Maven"));
    }
}
```

From the root directory (assuming `examples` and `out` exist):

```bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out \
    domain/src/main/java/com/example/acme/domain/Greeter.java \
    examples/GreeterProbe.java
java -cp out GreeterProbe
```

**Exact stdout:**

```text
Hello, Maven
```

The `javac` command puts both source files directly on the compile classpath and outputs bytecode under `out/`; it does not use the Maven reactor, parent, or `dependencyManagement`. Therefore, this experiment verifies the **Java code** but **does not** verify the multi-module Maven configuration. On Windows, create `out` in PowerShell and enter the `javac` command on one line; the `\` line continuations above are for Unix/macOS shells.

When moving to Maven `web-app`, there is no manual `javac` command: the **POM dependency** is responsible for making the compiler see the `domain` library during a standard build.

## 9. Spring Boot Starter Parent, BOM, and Corporate Parent

### 9.1. A POM Cannot Have Two Direct Parents

A Maven POM has only one direct `<parent>`. For multi-module projects using Spring Boot, two common strategies exist:

**Strategy A — Root inherits Spring Boot starter parent** (used in section 6):

```text
spring-boot-starter-parent:3.5.16
                |
                v
        acme-platform (root)
             /     \
          domain   web-app
```

Child modules inherit Boot dependency management and plugin defaults through the root. If the project requires an organization-wide parent, you can switch models:

**Strategy B — Root inherits corporate parent** and **imports the Spring Boot BOM** in the root's `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

This is an **alternative snippet** in a parent that does not inherit the Boot starter parent; it is not a complete POM and **is not** a runtime dependency of the application. With a corporate parent, you must separately configure the Java 17 compiler, UTF-8 encoding, test plugins, and the Spring Boot Maven Plugin `repackage` goal because **importing the BOM only brings dependency management, not the starter parent's plugin management/executions**.

### 9.2. When to Place Plugins in the Parent?

`<pluginManagement>` only **manages default versions and configurations** so modules applying the plugin can use them consistently. It does not mean every module will execute `repackage`.

If you place `spring-boot-maven-plugin` inside the root parent's `<build><plugins>` and allow its execution to be inherited, the `domain` library may try to repackage despite lacking a main class. That can cause build failures or create an executable artifact unsuitable as a dependency.

In a "library + application" model, the clean approach is to **declare `spring-boot-maven-plugin` only in `web-app`**, while managing its version/configuration via the starter parent or the root's `pluginManagement` when using a corporate parent.

This aligns with Spring Boot's recommendation: **do not use an executable Boot JAR as a library dependency**. In an executable JAR, classes typically live in `BOOT-INF/classes`; if you want to share code, move that code into an ordinary library module/JAR (`domain`) and declare a dependency on the library.

### 9.3. Parent and BOM Also Do Not Replace Aggregation

A POM that only imports the Spring Boot BOM without `<modules>` **does not automatically gather** the repository's modules into the reactor. Conversely, an aggregator with `<modules>` that does not import a BOM or inherit an appropriate parent **does not automatically manage** Spring Boot starter versions for children.

## 10. Common Multi-Module Design Variants

### 10.1. One Root Acting as Both Parent and Aggregator

Suitable for small teams or a single product with a unified release cadence:

```text
root pom:
  <parent> Spring Boot starter parent
  <packaging>pom</packaging>
  <modules>domain, web-app</modules>
  <dependencyManagement>internal modules</dependencyManagement>

domain pom:
  <parent>root</parent>
  ordinary jar

web-app pom:
  <parent>root</parent>
  <dependencies>domain + Boot starter</dependencies>
  Spring Boot plugin applied
```

The advantage is simplicity and a shared version; the trade-off is that modules can become tightly coupled to the upgrade/version cycle of the entire repository.

### 10.2. Separate Parent, Separate Aggregator

Suitable for multiple repositories/units sharing a corporate parent:

```text
org-parent (published POM)
   ^                  ^
   |                  |
domain           web-app
   ^                  |
   +------------------+   dependency web-app -> domain

all-modules/pom.xml
  <modules>../domain, ../web-app</modules>
  packaging=pom
  (not necessarily the parent of the two modules)
```

For example, `all-modules/pom.xml` only aggregates builds, while each module declares its own parent. The reactor still requires actual dependencies to sort properly. If `org-parent` is not in the reactor, Maven must download the parent from a repository or find the right `relativePath`.

### 10.3. Shared Module Releasing Independent Versions

Suppose `domain` is published as `com.example.acme:domain:2.1.0` and the app uses `web-app:1.0.0`. In that case, the dependency should point to the **exact released domain version**; do not blindly use `${project.version}`. Projects can reside in one repository or separate repositories depending on release policy.

With sources in the same repository yet independent versions, the reactor builds modules declaring compatible GAV/versions; if the dependency version does not match the current module artifact, Maven may download a version from a repository instead of using the reactor module as you expected. When bumping versions, inspect the dependency tree and release process.

## 11. Maven Reactor: Commonly Needed Commands

| Command | Meaning |
|---|---|
| `./mvnw clean verify` | Runs lifecycle through `verify` on the root + modules in the reactor |
| `./mvnw -pl :web-app -am verify` | Selects `web-app` and builds required upstream projects in the same reactor |
| `./mvnw -pl :domain -amd test` | Selects `domain` and adds modules in the reactor that depend on it |
| `./mvnw -pl :domain verify` | Only project `domain`; does not automatically select dependencies/dependents |
| `./mvnw -N validate` | Non-recursive: does not traverse modules; processes only the current POM |
| `./mvnw -rf :web-app verify` | Resumes the reactor from `web-app`; do not treat this as a substitute for rebuilding required dependencies |
| `./mvnw -pl :web-app help:effective-pom` | Reads the effective POM configuration of the application |
| `./mvnw -pl :web-app dependency:tree` | Inspects actual dependencies when artifacts/resolution are available |
| `./mvnw -pl :web-app -am install` | Builds/installs selected projects so artifacts reside in the local repository |

`-amd` stands for `--also-make-dependents`, useful when editing a library and wanting to run tests on modules that consume it. `-am` stands for `--also-make`, useful when focusing on building an app that needs library modules. `-pl` takes a project selector by path or `:artifactId`; never assume selecting an artifactId will make Maven add the dependency graph when `-am` is omitted.

**Note on selective builds:** Flags `-pl`, `-am`, and `-amd` control **reactor selection**; they do not modify `pom.xml` or declared dependency scopes. Nor do they turn a project outside the reactor into a new module. To build from another module's source, the aggregator must include that project in the reactor (or a properly connected build must exist).

## 12. Common Mistakes When Distinguishing Parent, Aggregator, and Dependency

| Symptom | Possible Cause | How to Check / Fix |
|---|---|---|
| `web-app` reports `Greeter` not found | Only `domain` in `<modules>`, missing `<dependency>` in `web-app` | Add proper dependency GAV, build with `-am` from root |
| Maven cannot find parent POM | Wrong `<parent>` coordinates, wrong `relativePath`, parent not published | Check GAV/relativePath, checkout root, Maven repositories |
| Root `mvn verify` does not build every module | Missing module path in `<modules>` or module outside reactor | Add exact relative path, invoke from the right root/aggregator |
| Building child module standalone fails to resolve internal dependency | Dependency not installed or build did not select reactor dependencies | Use `-pl :web-app -am verify` or install required artifacts |
| `domain` contains a Spring Boot executable JAR | `repackage` plugin applied to library or parent did not restrict inheritance | Apply Boot plugin only to the app module; keep domain as a plain JAR |
| `domain` pulls `starter-web` onto classpath | Parent declared starter directly in `<dependencies>` | Move version management to `dependencyManagement` and declare starters in modules that actually use them |
| `dependencyManagement` exists but `domain` is missing from dependency tree | Version management does not create a dependency | Add an actual `<dependency>` in the consumer |
| Reactor does not build in `<modules>` order | Dependency/parent/plugin relationships caused reactor re-sorting | This is usually right; inspect dependency edges instead of forcing list order |
| Reactor reports a dependency cycle | `domain` depends on `web-app` while `web-app` depends on `domain` | Extract shared API into a third module, remove reverse edge |
| Child POM sets a version different from parent causing internal mismatch | Module releases have different versions while dependency uses `${project.version}` | Align versions by policy or declare exact dependency versions |
| Only added Spring Boot BOM to parent and expected an executable JAR | BOM manages library versions, does not add the packaging plugin | Apply Spring Boot Maven Plugin + `repackage` execution on the app module |
| Parent uses `<pluginManagement>` yet plugin does not run | Plugin version is managed, not yet applied | Add the plugin under `<build><plugins>` in the module needing it |
| `java -jar domain.jar` fails to run | `domain` is a Java library with no application entry point | Run `web-app`'s executable JAR; `domain` is loaded only as a dependency |
| Build passes locally yet fails on CI | CI builds from a subdirectory, misses parent/modules, or uses different Maven/JDK | Run wrapper from root, inspect reactor summary and artifacts |
| Dependency tree shows an unexpected version | BOM, direct/nearest dependency mediation, or version override | Check `dependency:tree` and effective POM to find what manages the version |

### 12.1. Resolving Circular Dependencies Through Module Structure

Bad design:

```text
web-app -> domain
domain  -> web-app
```

The Maven reactor cannot find a valid topological build order when two modules require each other's classes. Do not "fix" this by changing `<modules>` order; the proper fix is to extract shared APIs/contracts into a module that does not depend on the app:

```text
             shared-api
             ^        ^
             |        |
          domain   web-app
             ^        |
             +--------+
```

Create only edges that are genuinely needed, keeping dependencies flowing from the application layer toward domain/libraries rather than the reverse.

## 13. Experiments: Change One Relationship at a Time to See the Difference

**Experiment A — Remove dependency in web-app:** Keep root `<modules>domain, web-app</modules>` and parent inheritance, yet **temporarily remove** `<dependency>com.example.acme:domain</dependency>` from `web-app`. Since the source still imports `Greeter`, compiling `web-app` will fail due to the missing classpath dependency. Conclusion: aggregation/inheritance do not replace dependencies.

**Experiment B — Remove module from aggregator:** Keep `<parent>` in `domain` and `web-app` and keep the dependency on `domain`, yet temporarily remove `<module>domain</module>` from root. The reactor no longer builds `domain` from source via the root aggregator; `web-app` can only resolve `domain` if the corresponding artifact already exists in a local/remote repository. Conclusion: inheritance and dependencies still exist, yet aggregation decides which projects build together.

**Experiment C — Parent differs from aggregator:** Have both modules inherit a corporate parent from a repository while an independent POM groups them with `<modules>`. Maven still builds them in the same reactor if the paths are valid. Conclusion: an aggregator does not have to be the parent.

**Experiment D — Management only, no usage:** In root, keep `<dependencyManagement>domain version</dependencyManagement>` yet remove the dependency declaration in `web-app`. The dependency tree does not automatically add `domain`. Conclusion: version management is not a classpath requirement.

**Experiment E — Reverse module order:** In `<modules>`, place `web-app` before `domain` while keeping the actual dependency. The Maven reactor still builds `domain` before `web-app`. Conclusion: actual dependency relationships matter more than XML declaration order.

Run configuration changes on a **copy of the project** or a test branch; after each run, **restore the original POMs** and run `./mvnw clean verify`. Do not make multiple changes simultaneously, or it will be hard to isolate causes.

## 14. Designing Parents and Modules in Real-World Spring Boot Development

**Version management:** When all modules ship in one release, a shared parent and `${project.version}` help avoid version drift. When modules release independently, you need separate dependency coordinates/version strategies, release notes, and compatibility matrices.

**Module boundaries:** Place logic independent of Spring Boot web into `domain`/`shared-core` when sensible. Allow applications/adapters to depend on domain, while preventing domain from depending back on apps or directly on controller/server libraries.

**Build plugins:** Only modules with a Spring Boot entry point need executable JAR/WAR repackaging. Shared libraries must produce library artifacts where compilers/consumers can find classes directly, not Boot executable archives.

**Testing rules:** Unit tests can live inside the domain module; controller/context tests live in the app module. Run the full reactor in CI to catch cross-module API breakages. `-pl -am` helps fast dev cycles, but do not skip tests on dependents of a shared library before releasing.

**Reproducibility:** Commit POMs/module paths/wrapper, pin the Java version, use trusted repositories, control SNAPSHOTs, and do not rely on an undetermined `~/.m2/repository` state. A machine with an old `domain` artifact in the local repo can accidentally mask a missing `-am` flag.

**Corporate parent:** If your organization mandates a parent, import the Boot BOM for dependency versions and configure compiler/plugins separately; do not declare two `<parent>` blocks. Even when the corporate parent is a remote artifact, the aggregator can still sit at the repository root.

**CI/CD:** A release pipeline should build all relevant modules in the reactor, run `verify`, inspect `Reactor Summary`, and select the right `web-app/target/*.jar` for deployment. Do not pass `domain/target/*.jar` into a `java -jar` pipeline as an application.

## 15. Multi-Module Structure Verification Checklist

1. **Parent GAV:** Each module points to the right parent, with a valid `relativePath` or published parent.
2. **Packaging:** Parent/aggregator is `pom`; library is `jar`; Spring Boot app is `jar` or `war` as required.
3. **Aggregation:** Root lists the right modules to build in `<modules>`, with existing paths.
4. **Classpath:** Every module using another module's classes has a `<dependency>` with the right coordinates, scope, and version.
5. **Version management:** `dependencyManagement` only manages versions and is not confused with an actual dependency.
6. **Plugin management:** `pluginManagement` manages versions/config and does not replace applying plugins in modules that need them.
7. **Reactor:** Run `-pl`/`-am`/`-amd` purposefully and inspect `Reactor Summary`.
8. **Spring Boot packaging:** Only the app module uses `spring-boot-maven-plugin` to repackage; libraries stay plain JARs.
9. **Clean checkout build:** `./mvnw clean verify` from root must pass with the right JDK and accessible repositories.
10. **Tests:** Module unit tests and application integration tests verify cross-module APIs.
11. **Dependency graph:** `dependency:tree` of `web-app` shows `domain` and no unexpected dependencies.
12. **Effective POM:** Inspect actual inheritance rather than guessing plugin/dependency versions.
13. **No cycles:** The module dependency graph contains no cycles.
14. **Publishing:** Internal module versioning and publish/install paths match repository/CI policy.

### Official Documentation

- [Apache Maven — Introduction to the POM: Inheritance & Aggregation](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Working with Multiple Modules & Reactor](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Dependency Mechanism and dependencyManagement](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot 3.5 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Build & executable JAR as a dependency](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Remember:** `<parent>` declares **configuration inheritance**, `<modules>` declares **reactor membership**, and `<dependencies>` creates **code usage and classpath relationships**. A root can be both parent and aggregator, yet Maven does not automatically wire dependencies between modules. For Spring Boot multi-module projects, keep libraries as plain JARs and repackage only the application module.