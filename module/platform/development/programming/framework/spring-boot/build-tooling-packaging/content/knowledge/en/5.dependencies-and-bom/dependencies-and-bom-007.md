# Distinguishing `spring-boot-starter-parent` from Standalone BOM Import in Maven

## 1. The Problem: Same Dependency Version Set, Two Different Ways to Manage the Build

A **Spring Boot project using Maven** must answer at least two separate questions:

1. **Which dependency versions are used?** For example, which coordinated versions of `spring-boot-starter-web`, Jackson, Spring Framework, logging, and test libraries should work together?
2. **Which configuration will Maven build with?** For example, what Java compiler target is used, which versions do test/packaging plugins run, how are resources filtered, and does `spring-boot:repackage` run during `package`?

Spring Boot offers two common mechanisms:

- **Parent inheritance:** declare `org.springframework.boot:spring-boot-starter-parent` in the `<parent>` section of `pom.xml`. The project receives **dependency management and many default build/plugin configurations** from the parent POM chain.
- **Standalone BOM import:** import `org.springframework.boot:spring-boot-dependencies` into `<dependencyManagement>` with `<type>pom</type>` and `<scope>import</scope>`. The project primarily receives **dependency version management rules**, while most build/plugin configuration must be declared by the project or its own parent.

**Core conclusion:** both approaches can yield **the same runtime library versions**, yet do not automatically yield **the same effective POM or executable JAR**. Which one you pick depends on whether the project needs to keep another Maven parent or wants Spring Boot to manage build defaults as well.

An easily confused naming detail: `spring-boot-starter-parent` is **not a starter added to the application classpath**; it is a POM to **inherit from**. `spring-boot-dependencies` is a **BOM (Bill of Materials)** used to coordinate versions; importing it **does not automatically add any starters** to `<dependencies>`.

## 2. Three Maven Concepts to Distinguish Before Comparing

### 2.1. `<parent>`: Inheriting Project Model Configuration

Maven allows a POM **one** direct `<parent>`. A parent can supply/inherit sections supported by Maven: `<properties>`, `<dependencyManagement>`, `<build><pluginManagement>`, inheritable plugin declarations, profiles, and other build settings. Maven merges them with the current project's configuration into the **effective POM**.

In Spring Boot, `spring-boot-starter-parent` inherits `spring-boot-dependencies` and adds convenient defaults for a Spring Boot application. Choosing it saves the project from declaring many standard settings manually.

### 2.2. `<dependencyManagement>`: Managing Versions Without Declaring Usage

Having a dependency in `<dependencyManagement>` means Maven knows to apply its managed version/scope/exclusions **when that dependency enters the graph**. It does not create a direct dependency for the application on its own.

Example:

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

The block above is **not enough** to run Spring Boot Web. To use the web starter, you must **declare usage**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

There is no `<version>` on the dependency because its version is already managed. Writing a direct `<version>` on the dependency uses that direct version for that declaration, which can break Boot's compatibility alignment.

### 2.3. `<pluginManagement>` Differs from `<dependencyManagement>`

- `<dependencyManagement>` manages **application dependencies** like starters, Jackson, SLF4J, JUnit.
- `<build><pluginManagement>` manages **build plugins** like `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-resources-plugin`, `spring-boot-maven-plugin`: plugin versions and settings can be supplied to plugins actually used.
- `<build><plugins>` declares **plugins participating in the build**. An entry in `pluginManagement` does not automatically execute all goals of that plugin.

Importing `spring-boot-dependencies` via `scope=import` does not import `<pluginManagement>` from that POM, nor does it import executions/filters/profiles from `spring-boot-starter-parent`.

## 3. Comparison Table by Verifiable Behavior

| Criterion | Inherit `spring-boot-starter-parent` | Import `spring-boot-dependencies` BOM |
| --- | --- | --- |
| Location in `pom.xml` | `<parent>`. | `<dependencyManagement><dependencies>` with `type=pom`, `scope=import`. |
| Can another parent be used simultaneously? | **Single direct parent**: must adjust the inheritance chain or pick another solution. | **Can** retain a corporate parent and import the BOM in the project. |
| Versions of Boot-managed dependencies | Yes, inherited from `spring-boot-dependencies`. | Yes, managed by the imported BOM. |
| Do starters appear on the classpath automatically? | No; still must be declared in `dependencies`. | No; still must be declared in `dependencies`. |
| Build plugin version/config management | Provides many useful defaults supplied by the parent. | **Does not include** parent plugin configuration; must declare in project or another parent. |
| Java compiler, UTF-8, `-parameters` defaults | Parent supplies defaults matching the Boot version. | Configure yourself or use corporate parent settings. |
| Maven resource filtering for Spring config | Parent includes settings tailored for `application*.properties/yml` files. | Does not automatically inherit those settings. |
| `spring-boot:repackage` during packaging | Parent already configures `repackage` execution; typically only declaring Spring Boot Maven plugin is needed. | Must declare the Spring Boot plugin **and** bind the `repackage` goal to the lifecycle. |
| Adjusting dependency versions via Boot properties | Can override properties used by parent/BOM, if the property exists in the chosen version. | Same-named property in the project **does not automatically alter values inside the imported BOM**; use explicit dependency/BOM management. |
| Build control | Less repetitive config, follows Boot parent conventions. | More explicit control; simultaneously requires maintaining plugins/toolchain/packaging explicitly. |
| Typical use case | New applications with no other mandatory parent. | Enterprises with a custom Maven parent, multi-module builds with an existing parent, or strict organizational build standards. |

**Two layers must always be checked independently:** the dependency tree speaks only to libraries; effective POM/plugin executions speak to **how Maven runs the build**. Both projects using the exact same version of `spring-boot-starter-web` does not prove identical packaging output.

## 4. Pattern A — Using `spring-boot-starter-parent`: Concise Configuration

The example below pins **Spring Boot 3.3.13** for a consistent illustration; this is a lesson version, **not a claim that it is the latest or still within its support window**. When starting a new application, pick a supported Spring Boot line per project policy and check corresponding JDK/Maven requirements.

Complete `pom.xml` for a Web application with one test:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>pom-contrast-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pom-contrast-demo</name>
    <description>Comparison of Spring Boot Maven dependency management options</description>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Why this pattern is concise:

1. `<parent>` lets Maven inherit dependency management from Boot, so starters omit versions.
2. Parent 3.3.13 defines defaults for Java 17 compilation, UTF-8 encoding, parameter metadata flags, and matching plugin/lifecycle configuration; `java.version` is set explicitly for clarity.
3. Declaring `spring-boot-maven-plugin` in `<plugins>` activates the parent's configuration. The parent already configures an execution with ID `repackage` to package an executable archive during the lifecycle.
4. `spring-boot-starter-test` is only in `test` scope and does not belong in the runtime JAR.
5. `<relativePath/>` tells Maven to resolve the parent by GAV from repositories instead of probing a parent directory `pom.xml` that the project did not intend to use.

Distinguish **"the parent preconfigures the `repackage` execution"** from **"no need to declare the plugin."** With Spring Boot starter parent as shown, you still declare `spring-boot-maven-plugin` for the execution to apply. A POM omitting the plugin may pass `mvn package` while producing only a plain JAR, depending on inherited config.

### 4.1. Verifying Pattern A Right Away

~~~bash
# macOS/Linux; using Maven Wrapper generated/committed in repo
./mvnw help:effective-pom -Doutput=effective-parent.xml
./mvnw dependency:tree
./mvnw clean verify
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar
~~~

On Windows use `mvnw.cmd`. In the effective POM, look for `spring-boot-maven-plugin` and the `repackage` execution; in the JAR, look for `BOOT-INF/classes` and `BOOT-INF/lib`. `clean verify` runs through `package`, so packaging normally runs as long as the plugin is bound as above and not skipped. **These are commands for the learner to run; they are not actual outputs observed within this article.**

## 5. Pattern B — No Boot Parent, BOM Import Only

Keep the same module with `groupId=com.example`, `artifactId=pom-contrast-demo`, and Java 17. The POM below **does not use the Boot parent**; it builds on Maven's Super POM, imports the BOM, and explicitly declares **build plugin versions, compiler, test runner, and Spring Boot repackaging execution**.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>pom-contrast-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>pom-contrast-demo</name>

    <properties>
        <spring-boot.version>3.3.13</spring-boot.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.1. Which Settings Does Pattern B Have to Carry Explicitly?

- **BOM import:** manages versions of `spring-boot-starter-web`, `spring-boot-starter-test`, and other dependencies in Boot's catalog. It **does not** register the Boot Maven plugin.
- **Compiler:** `maven-compiler-plugin` with `release=17` ensures code compiles against Java 17 APIs/bytecode; `parameters=true` preserves parameter name metadata for frameworks relying on reflection.
- **Testing:** `maven-surefire-plugin` 3.2.5 can run `spring-boot-starter-test`'s JUnit Platform/Jupiter tests under suitable defaults.
- **JAR packaging:** `maven-jar-plugin` produces the regular JAR during `package`. Then `spring-boot-maven-plugin` with the `repackage` goal builds the executable Spring Boot JAR from that archive.
- **Plugin versions:** declared explicitly, because BOM import does not inherit plugin versions from the Spring Boot parent. The example pins compatible plugin versions so learners see where they come from; real projects should choose company-approved versions and verify compatibility.
- **Resources:** the example does not enable filtering for config files; if you need Maven variable substitution in `application.properties`/`application.yml`, design `maven-resources-plugin`/resource filters safely yourself.

### 5.2. Why Must the `repackage` Execution Be Declared?

The `repackage` goal **repackages an existing archive** so Spring Boot includes its launcher and needed dependencies. Declaring the plugin without binding the goal to a lifecycle **is not enough** to ensure `mvn package` creates an executable JAR when not using the Boot parent.

When `<executions>` above is present, `repackage` runs during the `package` phase (the goal's default phase), after regular JAR creation. If a project customizes ordering or adds `maven-jar-plugin` executions in the same phase, ensure the original JAR is built before repackage runs.

Commands for POM B:

~~~bash
./mvnw help:effective-pom -Doutput=effective-bom.xml
./mvnw dependency:tree
./mvnw clean verify
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar
~~~

**Expected outcome once Java source/tests below are present:** both A and B resolve starters from the same 3.3.13 BOM, compile for Java 17, run tests, and produce an executable archive. Achieving that same outcome comes from **POM B's explicit configuration**, not because BOM import brings along parent build behavior.

To compare **in an exercise**, run A and save both pieces of evidence—`effective-parent.xml` and the dependency tree; replace the POM with B, run clean, and save `effective-bom.xml`. Never place two POMs in the same project expecting Maven to pick the right one.

## 6. One Shared Program to Test Both POMs

Use the exact same source code in **one project at a time** so Java errors are never mistaken for POM errors.

File layout:

~~~text
pom-contrast-demo/
  pom.xml
  mvnw                 (project Maven Wrapper)
  mvnw.cmd
  .mvn/wrapper/...
  src/main/java/com/example/demo/DemoApplication.java
  src/test/java/com/example/demo/DemoApplicationTest.java
~~~

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`src/test/java/com/example/demo/DemoApplicationTest.java`:

~~~java
package com.example.demo;

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
class DemoApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

The program uses `spring-boot-starter-web` and `spring-boot-starter-test`, compatible with the **API structure of the Boot 3.3.13 example**. `@SpringBootTest` loads the application context; `@AutoConfigureMockMvc` sets up MockMvc to test requests without opening a real HTTP listener; the test verifies status 200 and body `pong`. `src/test/java` does not enter the runtime archive as application code.

With a Maven Wrapper and a **compatible JDK 17**:

~~~bash
./mvnw clean verify

# Inspect executable JAR structure
jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar

# Open another terminal while the app runs:
java -jar target/pom-contrast-demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

Once the app starts, in another terminal:

~~~bash
curl -i http://localhost:8085/ping
~~~

**Expected behavior:** HTTP 200 with the exact response body `pong`. Startup logs, line order, PID, and timing are not fixed output; record your actual output. If `java -jar` reports a missing main manifest attribute/launcher or class, check whether `repackage` ran and whether you picked the right JAR file after `package`. Note that this is a hands-on guide and technical expectation, **not a report of Maven having been executed in the learner's environment**.

## 7. How Maven Decides Versions: Properties, Local Management, and Conflicts

### 7.1. When Inheriting Parent: Overriding a Boot-Managed Property

Suppose a project uses Boot parent and has a verified reason to change the SLF4J version; an example of the *mechanism* is:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

**Why it works:** along the **inheritance** chain, properties defined in the child can be interpolated into managed versions in the parent model. However, only properties that actually exist and are referenced by the BOM/parent in the chosen version take effect. **Do not treat the version above as advice to upgrade/downgrade SLF4J:** Spring Boot is tested against a specific dependency set; overriding can break compatibility with Logback/Spring Framework or other starters.

To see which properties exist in your Spring Boot version, consult the dependency-version properties reference for that **exact version**, then check `effective-pom` and `dependency:tree`.

### 7.2. When Only Importing the BOM: Project Properties Do Not Override BOM Internals

Suppose in Pattern B you write:

~~~xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

`spring-boot.version` here **takes effect** because the **current POM itself** puts `${spring-boot.version}` in the BOM import coordinates and Boot plugin.

Conversely, `slf4j.version` **does not alter the SLF4J version inside the imported BOM's POM**. An imported BOM is resolved as an independent model; Maven imports the BOM's dependency management entries into the project without re-evaluating project properties against an inherited parent.

To manage a specific dependency differently from the BOM in this case, declare the **project's own management entry** before the BOM import entry. The example below illustrates the structure (Spring Boot and SLF4J versions are sample numbers):

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Override declared in project, before BOM import -->
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This overrides only the listed **`org.slf4j:slf4j-api`** coordinates and **does not synchronize all SLF4J modules**. If a library suite is managed by a specialized BOM, you may need to import a verified matching BOM before the Spring Boot BOM according to Maven's precedence order. Avoid swapping individual artifacts in a complex ecosystem before understanding overall compatibility.

### 7.3. Practical Precedence Rules to Remember

1. **A version declared directly** on a used dependency can override the managed version for that declaration.
2. **Local `<dependencyManagement>`** for a coordinate can apply the desired version over an imported entry.
3. **When importing multiple BOMs with overlapping entries**, import order and Maven management rules decide which entry is kept; for imported BOMs at the same level, the entry appearing **first** normally wins for overlapping coordinates.
4. **Dependency mediation** is a separate step: when no managed version applies, Maven evaluates dependency paths via rules like nearest definition; do not think of BOM import as a command forcing every transitive dependency at all costs.
5. Check the **resolved dependency tree**, rather than just eyeballing `pom.xml` or assuming two BOMs are "definitely equivalent."

~~~bash
# View resolved dependencies, including transitive dependencies
./mvnw dependency:tree

# Narrow output when investigating SLF4J
./mvnw dependency:tree -Dincludes=org.slf4j
~~~

If the project manages versions via a corporate parent, inspect the **effective POM**, because that parent can inject entries or plugin configurations differing from both examples.

## 8. Most Practical Difference: Build Plugins and Executable Packaging

Maven has two distinct flows that learners often lump together mistakenly:

~~~text
Spring Boot parent
  -> dependencyManagement  -> starter/library versions
  -> pluginManagement      -> plugin versions/configs
  -> plugin/lifecycle      -> defaults for resources, compiler, repackage...
                                 |
                         project declares Boot plugin
                                 |
                         mvn package -> executable archive
~~~

~~~text
Import Spring Boot BOM
  -> dependencyManagement  -> starter/library versions
                                 |
  + project/custom parent must declare compiler, test, resources,
    Spring Boot Maven plugin, and repackage execution
                                 |
                         mvn package -> executable archive
                         (once properly configured)
~~~

In short, **`<dependencyManagement>` does not run the `repackage` goal**. Even in a project without the Spring Boot parent, the plugin snippet below is only a **plugin declaration** and does not bind the goal during `package`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
</plugin>
~~~

Proper standalone configuration for executable packaging requires the `repackage` goal as in Pattern B. On the other hand, if already using the Boot parent, adding another `repackage` execution with a different ID than the parent's execution can run the goal twice; when customizing the existing execution, reference the exact ID `repackage`.

**How to verify:** do not stop at `BUILD SUCCESS`—inspect `target/*.jar` with `jar tf` and actually run `java -jar`. A Spring Boot executable JAR normally contains `BOOT-INF/classes/` and `BOOT-INF/lib/`. A plain JAR succeeding in `package` can still lack the launcher or required runtime dependencies.

Beyond JARs, WARs, layered JARs, OCI images, and native images require additional configuration/plugins/goals. Importing a BOM does not enable them automatically; even using the parent does not create every package format by default.

## 9. Differences in Compiler, Testing, Resource Filtering, and Build Reproducibility

### 9.1. Java, Encoding, and Parameter Metadata

In Spring Boot 3.3.13, the starter parent defaults to compiling with Java 17, UTF-8 encoding, and `-parameters`. Importing the BOM **does not set** any of those values. Without compiler configuration, compiler plugin versions/Maven defaults may differ from expectations or fail to produce the needed bytecode.

In Pattern B, the settings:

~~~xml
<maven.compiler.release>17</maven.compiler.release>
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

and `<parameters>true</parameters>` on `maven-compiler-plugin` reproduce those essential characteristics, yet **do not equate to copying the entire parent configuration**. If the application requires generated sources, annotation processors, or test-specific compiler options, they must still be configured separately.

### 9.2. JUnit and Surefire/Failsafe

`spring-boot-starter-test` manages **test dependencies**; Maven's test discovery also depends on **maven-surefire-plugin**, the JUnit Platform engine, and test configuration. In Pattern B, the Surefire version is declared explicitly to avoid relying on Maven/Super POM defaults. The parent usually manages plugin versions and configuration accordingly.

**Integration tests do not appear automatically** merely by using the parent or importing the BOM. If using Failsafe, Testcontainers, or profiles/separate source sets, configure them explicitly and inspect test reports for the `integration-test`/`verify` phases. All test conclusions must rest on actual reports.

### 9.3. Filtering Spring Boot Configuration Files

An `application.properties` file may contain Spring placeholders such as:

~~~properties
server.port=${PORT:8080}
spring.application.name=pom-contrast-demo
~~~

`${PORT:8080}` is a placeholder resolved by Spring **when the application runs**. If Maven resource filtering inadvertently treats `${...}` as a Maven property, it risks altering or colliding with runtime values.

Spring Boot starter parent configures custom resource filtering using delimiters like `@project.version@` for build data when needed, avoiding typical clashes with Spring placeholders. When only importing the BOM, you must decide whether to enable filtering, pick delimiters, and choose which resources are filtered; **never blindly copy standard Maven resource filtering defaults**.

Illustrative **intentional template**:

~~~properties
app.build.version=@project.version@
app.runtime.port=${PORT:8080}
~~~

Expect `@project.version@` to become the build version **only when matching resource filtering is configured**; a standalone BOM import does not ensure it. After packaging, inspect the file inside the archive rather than assuming from YAML/properties in source.

### 9.4. Reproducibility and Corporate Governance

- Commit and use **Maven Wrapper** alongside a supported JDK/toolchain; neither parent nor BOM replaces the Wrapper.
- Pin versions of the Boot BOM, Spring Boot Maven plugin, and build plugins controlled by the project; avoid pairing Boot BOM version X with an untested plugin version Y.
- A corporate parent may supply plugin versions, repositories, profiles, enforcers, security gates, distribution management, or internal release rules. Importing the BOM preserves those rules while **not guaranteeing they will not conflict** with Boot.
- Plugin repositories differ from dependency repositories; identical dependency trees do not prove identical plugin versions.
- In a multi-module Maven reactor, decide **which modules use the BOM** and **which modules are runnable applications**. Never apply `repackage` to library modules that lack a main class.
- To verify equivalence between two setups to the required level, compare resolved dependency trees, plugin executions, compiler levels, test discovery, JAR structure, and runtime smoke tests.

## 10. Multi-Module and Corporate Parent Scenarios: Picking the Right Inheritance Level

Suppose a company requires every Maven module to inherit `com.company:company-parent` for compliance with internal standards. Each Maven module still has only one direct `<parent>`, so `spring-boot-starter-parent` cannot be added as a **second parent**.

Common options:

1. **Keep company parent; import the Boot BOM** in the corporate parent or appropriate module, and declare build plugins/repackage in application modules. Library modules do not need `repackage`.
2. **Company parent itself inherits Boot starter parent** if the organization intentionally designs that inheritance chain. Child modules then receive Boot defaults through the parent chain, though Boot version pinning must be coordinated organization-wide.
3. **No mandatory parent:** use the starter parent directly on standalone apps to minimize maintained boilerplate.
4. **Need centralized plugin control differing from Boot:** corporate parent + BOM import usually integrates more cleanly with existing build rules, provided the team explicitly pins plugin versions and quality gates.

Illustrative POM *fragment* for an application module inheriting an internal parent (not a standalone runnable POM):

~~~xml
<parent>
    <groupId>com.company</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>

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

This is an **illustrative fragment** and does not mean `com.company:company-parent:1.0.0` exists in your repository. In practice, check what rules the internal parent enforces on `dependencyManagement`, `pluginManagement`, Maven Enforcer, Java target, and publishing. Place the BOM in the shared parent when all modules should follow one version set; if only Spring Boot modules need the BOM, scope it accurately to those modules.

### Role Division Rules in a Maven Reactor

- **Library module:** typically outputs a standard JAR supplying classes to other modules; should not be forced into an executable JAR.
- **Application module:** holds the Spring Boot main class, adds starters, `repackage` plugin, and runnable packaging config.
- **Parent/aggregator POM:** coordinates dependency/plugin management and module lists; does not necessarily hold application code or an artifact runnable via `java -jar`.

Do not confuse `<modules>` (aggregation) with `<parent>` (inheritance): a reactor root listing modules is not automatically the parent of every module unless each module declares inheritance. Keeping this boundary clear places the BOM at the right level and avoids losing management effect.

## 11. Verification Exercise: Measure Three Results, Don't Just Eyeball the POM

Use the **same Java/test source** from section 6; try POM A, then POM B. For each approach, record evidence:

| Verification | Command/Observation | What to Confirm |
| --- | --- | --- |
| **Dependency versions** | `./mvnw dependency:tree` | Starter/Jackson/Spring/JUnit use BOM-managed versions; no missing-version dependencies. |
| **Effective POM** | `./mvnw help:effective-pom -Doutput=effective-pom.xml` | Differences in parent chain, compiler/`pluginManagement`, resource settings, and `repackage` execution. |
| **Toolchain** | `./mvnw -version`, compiler config | Maven runs on a compatible JDK, bytecode target is Java 17. |
| **Tests** | `./mvnw clean verify`, `target/surefire-reports/` | JUnit tests are discovered, executed, and PASS; not skipped. |
| **Artifact** | `jar tf target/pom-contrast-demo-0.0.1-SNAPSHOT.jar` | JAR has loader/manifest and runtime dependencies appropriate for Spring Boot. |
| **Runtime** | `java -jar ... --server.port=8085`; `curl -i localhost:8085/ping` | Starts cleanly and `GET /ping` returns status 200 with body `pong`. |

If A passes while B fails, diagnose by root cause:

- **`maven-compiler-plugin` error:** check plugin version, `release`, running JDK, and corporate parent.
- **Tests do not run or engine not found:** check Surefire/Failsafe plugin and reports rather than assuming from `starter-test`.
- **Plain JAR / `no main manifest attribute`:** check `spring-boot-maven-plugin` `repackage` execution in effective POM and Maven `package` output.
- **Wrong Spring Boot plugin version:** match plugin version/property with the BOM.
- **Resources modified unexpectedly:** inspect filtering/delimiters and the file contents inside the archive.
- **Dependency conflict:** inspect `dependency:tree` and effective `dependencyManagement` sources; check corporate parent, other imported BOMs, and direct dependency versions.
- **Green build yet fails to run:** runtime config, profile, port, Java version, or external services do not match; this is a separate verification layer.

### Self-Check Questions

1. Why is `spring-boot-starter-parent` a POM in `<parent>`, while `spring-boot-dependencies` is imported in `<dependencyManagement>`?
2. When importing the BOM, why must you still declare `spring-boot-starter-web` in `<dependencies>`?
3. Why can the same BOM produce the same dependency tree while only one project produces an executable JAR?
4. Maven allows only one direct parent: if a project must use a corporate parent, how does it maintain dependency alignment with Spring Boot?
5. Why does overriding `slf4j.version` work with the parent yet fail to modify an imported BOM directly?
6. Which two types of versions do `pluginManagement` and `dependencyManagement` govern? What role does `<plugins>` play?
7. Without starter parent, what must be declared so Java 17, JUnit tests, resource handling, and `repackage` work properly?
8. In a reactor containing library modules, why should you not apply the Spring Boot executable `repackage` goal to every module?
9. Which contents of `effective-pom`, `dependency:tree`, and the JAR should you check before concluding two setups are equivalent in quality?
10. If `mvn package` still creates a plain JAR when using the parent, what would you check first?

**Completion criteria:** the learner can choose the right model for project requirements, write the corresponding POM, explain where both dependency versions **and** plugin versions originate, verify the `repackage` execution along with tests/reports, and run the resulting executable artifact. Mastery means verification evidence backs up your claims, not just that XML syntax validates.

## 12. Reference Documentation

- [Spring Boot Maven Plugin — Using the Plugin: Parent vs BOM](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)

**Takeaway:** choosing parent vs. BOM import is not a quality badge. Build quality is measured by **effective POM, dependency tree, compiler/test evidence, archives, and runtime behavior**. The parent cuts down boilerplate; BOM import gives clearer control when projects have another parent, while shifting responsibility for configuring the rest onto the development team.