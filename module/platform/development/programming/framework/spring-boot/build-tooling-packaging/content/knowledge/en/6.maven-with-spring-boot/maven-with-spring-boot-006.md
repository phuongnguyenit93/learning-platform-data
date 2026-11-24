# Binding `repackage` to `package` Without Using Spring Boot Starter Parent (Maven)

## 1. Lesson Goal

Topic: **Binding `repackage` to `package` without using starter parent.**

In a Maven-based Spring Boot project, you may not inherit `org.springframework.boot:spring-boot-starter-parent` because your organization uses its own parent POM or you want independent plugin version control. The project can still use Spring Boot starters and the Spring Boot BOM. However, importing the BOM or declaring starters **does not make Maven automatically run the `spring-boot:repackage` goal**.

The ultimate goal is running a single command:

~~~bash
mvn clean package
~~~

and producing an **executable Spring Boot JAR** containing code, runtime dependencies, and the Spring Boot launcher, ready to start with:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar
~~~

After this lesson, you will know how to:

- Separate the roles of starter, BOM, Maven parent, Maven build plugin, and goal execution.
- Bind `spring-boot-maven-plugin:repackage` to the `package` phase in a `pom.xml` **without starter parent**.
- Explain the `jar:jar → spring-boot:repackage` order and the requirement for a source JAR/WAR.
- Run and verify a Spring Boot project with a complete POM, Java 17, and a unit test.
- Inspect the effective POM, Maven logs, `.jar` files, manifest, `BOOT-INF`, and `java -jar` output.
- Apply this pattern in corporate parents, multi-module builds, classifiers, CI builds, and troubleshooting.

**Example versions:** Spring Boot **4.1.2**, Java **17**, Maven **3.6.3 or later** per the Spring Boot 4.1.2 system requirements documentation. The starter used is `spring-boot-starter-webmvc` per Spring Boot 4. Do not assume newer Java or Boot versions work without checking compatibility requirements.

## 2. Separating Core Roles

| Component | Where Is It Placed? | Role | Automatically Binds `repackage`? |
| --- | --- | --- | --- |
| `spring-boot-starter-webmvc` | `<dependencies>` | Selects the dependency set for writing Spring MVC | No |
| `spring-boot-dependencies` BOM | `<dependencyManagement>` with `<type>pom</type>` and `<scope>import</scope>` | Manages dependency versions | No |
| `spring-boot-maven-plugin` | `<build><plugins>` | Provides goals like `repackage`, `run`, `build-image` | Not enough without a goal execution |
| `<execution>` on the Maven plugin | `<executions>` inside the plugin declaration | Binds one or more goals to a build phase | **Yes**, when declared properly |
| `spring-boot-starter-parent` | `<parent>` | Inherits dependency management, plugin management, and a pre-configured `repackage` execution | Has a pre-configured execution when the plugin is activated |

**Key point to remember:** the `spring-boot-dependencies` BOM provides dependency versions, while `spring-boot-starter-parent` adds Maven/plugin configuration. **Importing the BOM does not bring in the starter parent's plugin management and executions.**

A project can import the BOM as follows:

~~~xml
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
~~~

After importing, Maven can resolve dependencies managed by the BOM, for example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
~~~

without writing `<version>` on the dependency. Nevertheless, the project **still must** declare and configure the build plugin to generate an executable JAR.

## 3. What Happens If `repackage` Is Missing?

For `<packaging>jar</packaging>`, Maven has default lifecycle goals; during the `package` phase, `maven-jar-plugin:jar` builds a **regular JAR**. It typically contains compiled classes and resources in standard Java package layout, such as:

~~~text
target/boot-no-parent-1.0.0.jar
└── com/example/demo/DemoApplication.class
~~~

A regular JAR **does not necessarily** contain runtime dependencies, the Spring Boot loader, or an executable Spring Boot manifest. If you run:

~~~bash
mvn clean package
java -jar target/boot-no-parent-1.0.0.jar
~~~

with a configuration that has not bound `repackage`, the build may still report `BUILD SUCCESS`, yet `java -jar` fails to run as expected—for instance, due to a missing main manifest attribute or missing runtime classpath.

Conversely, when `repackage` runs properly, the Spring Boot archive has this typical layout:

~~~text
target/boot-no-parent-1.0.0.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/com/example/demo/DemoApplication.class
├── BOOT-INF/lib/...
└── org/springframework/boot/loader/...
~~~

**`jar:jar` builds the source archive; `spring-boot:repackage` repackages the source archive.** Repackaging does not compile Java and does not replace the goal that builds the initial JAR/WAR.

## 4. Maven Lifecycle and Execution Order

Typical phases when building a `jar` project:

| Maven Phase | Goal or Activity | Output |
| --- | --- | --- |
| `validate` | Validates POM and runs bound goals if any | Valid configuration |
| `process-resources` | `resources:resources` | `target/classes` with resources |
| `compile` | `compiler:compile` | `.class` files |
| `test-compile` | `compiler:testCompile` | Test classes |
| `test` | `surefire:test` | Test reports |
| `package` | `jar:jar` | Plain JAR |
| `package` | **`spring-boot:repackage`** when bound | Executable Spring Boot JAR |
| `verify` | Additional configured checks | Verification results |

Maven executes all phases preceding the requested phase. Thus, invoking `mvn package` runs up through `package`, including tests (unless skipped by configuration). Invoking `mvn verify` also passes through `package` before running configured verification goals.

For `jar` packaging, default bindings such as `jar:jar` execute before additional goals bound to the same phase in the POM. If a project has custom executions of `maven-jar-plugin` and the Spring Boot plugin in `package`, Spring Boot documentation emphasizes **declaring the Jar Plugin before the Boot Plugin** so the source JAR is ready before `repackage`.

Distinguish clearly:

~~~text
mvn clean package
    -> resources -> compiler -> test -> jar:jar -> boot:repackage

mvn spring-boot:repackage
    -> invokes goal alone; does not guarantee source JAR exists

mvn package spring-boot:repackage
    -> packages then invokes goal explicitly; useful when goal is NOT yet bound
    -> avoid redundant invocation when POM already binds repackage
~~~

**The `repackage` goal has a default phase of `package`**, but this metadata **does not mean** merely listing `spring-boot-maven-plugin` in `<plugins>` makes Maven run the goal automatically. You need an `<execution>` with `<goals><goal>repackage</goal></goals>`, or an execution inherited from a parent.

## 5. Minimal Configuration Snippet to Add to the POM

In an application module using `jar` or `war` packaging, add the following plugin inside `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Each field has a distinct meaning:

- `groupId` and `artifactId` identify **Spring Boot Maven Plugin**, not a starter dependency.
- `version` selects the plugin version. When importing **only** the BOM, you must provide the plugin version directly or through other plugin management; the BOM does not supply the plugin version.
- `executions` tells Maven this goal participates in the build lifecycle.
- `id=repackage` names the execution, useful when inspecting logs and merging inherited configuration.
- `phase=package` states exactly when it runs. The goal metadata also defaults to this phase, so specifying `phase` is **explicit and valid**, though optional in basic setups.
- `goals/goal=repackage` tells Maven to run the goal.
  
**Common mistake:** writing only:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
</plugin>
~~~

in a project with no inherited execution, and expecting `mvn package` to repackage automatically. A bare plugin declaration allows invoking the goal explicitly, but does not add the desired lifecycle binding to `package`.

### Is `<pluginManagement>` Enough?

No. `<build><pluginManagement>` typically **defines default versions and configurations**, without activating an unreferenced plugin to run in the current module. If a corporate parent places the Boot plugin in `pluginManagement`, the application module still needs to activate the plugin in `<build><plugins>` and ensure the `repackage` execution is present.

## 6. Complete POM Example **Without Starter Parent**

Standalone Maven project using Java 17 and Spring Boot 4.1.2:

~~~text
boot-no-parent/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/demo/DemoApplication.java
│   └── test/
│       └── java/com/example/demo/DemoApplicationTest.java
└── target/      # Created by Maven after build
~~~

Complete **`pom.xml`**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>boot-no-parent</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>4.1.2</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <phase>package</phase>
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

Why this configuration builds standalone:

1. It sets `<packaging>jar</packaging>`, meaning Maven creates a source JAR during `package`.
2. The BOM imports the appropriate versions of Spring Boot starters; starters do not declare versions themselves.
3. `maven.compiler.release` selects Java 17; `maven-compiler-plugin` is version-pinned to avoid outdated defaults.
4. `maven-surefire-plugin` version 3.6.1 can run JUnit Platform/JUnit Jupiter, including the JUnit 6 line that Spring Boot 4 may use.
5. `maven-jar-plugin` is declared before the Spring Boot plugin; `jar:jar` produces output for Boot to process.
6. `spring-boot-maven-plugin` specifies its version and an **execution bound to the `package` phase**. No starter parent inheritance is needed for that binding.
7. There is no `<parent>` in this complete POM. The POM **is not just a snippet**; it works directly for a new project matching the example layout.

Other default plugins such as Maven Clean Plugin may be governed by your Maven version or another parent. This example pins the plugins directly affecting compile/test/package, while enterprise projects should pin all plugins per organizational policy.

## 7. Runnable Java 17 Code and Unit Test

**File `src/main/java/com/example/demo/DemoApplication.java`**:

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

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Boot without parent";
    }
}
~~~

**File `src/test/java/com/example/demo/DemoApplicationTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DemoApplicationTest {
    @Test
    void helloReturnsExpectedText() {
        DemoApplication app = new DemoApplication();
        assertEquals("Hello from Boot without parent", app.hello());
    }
}
~~~

This is a **unit test** on the method returning the string, without starting an HTTP server. Therefore, this test proves only the method's logic, not that the executable JAR is handled properly by the Boot loader. Later steps verify that with `java -jar` and an HTTP request.

When running `mvn clean package`, Maven runs tests unless you pass skip flags. The name `DemoApplicationTest` matches Surefire's standard test discovery pattern. In this example, `spring-boot-starter-test` brings in test dependencies managed by the BOM.

## 8. Running the Build and Reading Logs Properly

In the directory containing `pom.xml`, with appropriate Maven and JDK:

~~~bash
mvn -version
java -version
mvn clean package
~~~

A valid build log will show goals in a logical sequence like the following (this **is not** fixed verbatim stdout):

~~~text
maven-resources-plugin:3.3.1:resources
maven-compiler-plugin:3.14.1:compile
maven-compiler-plugin:3.14.1:testCompile
maven-surefire-plugin:3.6.1:test
maven-jar-plugin:3.4.2:jar
spring-boot-maven-plugin:4.1.2:repackage (repackage)
BUILD SUCCESS
~~~

Maven also outputs resource/testResource goals and messages about dependencies, artifact downloads, test counts, and build timing. Those messages vary by environment, Maven version, and cache. What matters for this topic is that **the Boot `repackage` goal is automatically invoked in `package` right after `jar:jar`**, without a second command.

Default post-build files:

~~~text
target/
├── classes/com/example/demo/DemoApplication.class
├── test-classes/com/example/demo/DemoApplicationTest.class
├── surefire-reports/...
├── boot-no-parent-1.0.0.jar
└── boot-no-parent-1.0.0.jar.original
~~~

- `boot-no-parent-1.0.0.jar` is the default repackaged **executable JAR**.
- `boot-no-parent-1.0.0.jar.original` is the **original JAR** before repackaging; do not choose this file for deployment.
- Maven version, `finalName`, classifier, or other build plugins can change filenames. When verifying, cross-check `artifactId`/`version`/`finalName` and the current build's log.
- If `repackage` did not run, `target/boot-no-parent-1.0.0.jar` may still exist as a plain JAR: **the mere existence of the filename does not prove success**.

If the project repository includes Maven Wrapper, you can run `./mvnw clean package` or `mvnw.cmd clean package` on Windows. This example does not generate a wrapper.

## 9. Evidence-Based Verification of the Executable Artifact

### 9.1. Inspecting JAR Contents

~~~bash
jar tf target/boot-no-parent-1.0.0.jar
~~~

Output must contain these areas:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/demo/DemoApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

`BOOT-INF/classes` holds application classes/resources; `BOOT-INF/lib` holds nested runtime JARs; `org/springframework/boot/loader` holds the Boot launcher. These are the hallmarks of a standard-layout Spring Boot executable JAR.

### 9.2. Inspecting the Manifest

Read `META-INF/MANIFEST.MF` from the archive using an available tool (such as `unzip -p target/boot-no-parent-1.0.0.jar META-INF/MANIFEST.MF` on machines with `unzip`). Typical manifest:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

`Main-Class` points to the Boot launcher, while `Start-Class` points to the application class with `main`. The Boot plugin manages these entries during `repackage`; if you need to specify the main class explicitly, configure `mainClass` on the Boot Maven Plugin.

### 9.3. Running at Runtime and Testing HTTP

In the first terminal:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar
~~~

Wait for the server to start, then in a second terminal:

~~~bash
curl -fsS http://localhost:8080/hello
~~~

**Exact HTTP response body of the endpoint**:

~~~text
Hello from Boot without parent
~~~

The controller returns a string without a trailing newline. Terminal tools or prompts may append their own display formatting; Spring Boot startup logs vary by environment and must not be treated as fixed stdout.

If port 8080 is already in use, run:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar --server.port=8081
~~~

and test `curl -fsS http://localhost:8081/hello`. On Windows PowerShell, use `curl.exe` to avoid PowerShell's alias. This HTTP test is a **smoke test**, distinct from the unit test in Section 7.

## 10. Verifying Binding Through Effective POM

The visible POM can differ from the model Maven uses after parent inheritance, property resolution, profiles, and plugin management. To confirm:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Open `effective-pom.xml` in the project workspace and check:

- `spring-boot-maven-plugin` is declared inside `build/plugins` of the application module;
- the resolved Boot plugin version is `4.1.2` in this example;
- execution ID `repackage` has goal `repackage` and phase `package`;
- no extra execution accidentally runs `repackage` a second time;
- `skip`, `classifier`, and `mainClass` configurations if present.

When using a corporate parent, the plugin version may be managed in `build/pluginManagement`; the **effective POM** reveals the merged configuration. If a build passes green yet the log only shows `jar:jar`, the effective POM is the first place to check.

You can check the dependency graph separately:

~~~bash
mvn dependency:tree
~~~

If the dependency graph is right yet no executable archive is produced, the issue almost certainly lies in **plugin/lifecycle binding**, not the BOM.

## 11. Applying This in Companies with a Corporate Parent

Suppose an organization requires a parent POM containing repositories, policies, and plugin config. Maven allows only one direct parent; **you cannot declare both the corporate parent and the starter parent in two `<parent>` elements**.

Implementation order:

1. Keep the organization's parent POM.
2. Import `spring-boot-dependencies` into `dependencyManagement` of the module or an appropriate parent.
3. Declare web/test starters in `dependencies` as needed.
4. Ensure `spring-boot-maven-plugin` has its version managed by the corporate parent or declared on the module.
5. Place the plugin in `build/plugins` of the application module and add the `repackage` execution bound to `package` **if no equivalent inherited execution exists**.
6. Run `mvn help:effective-pom` to inspect the merged configuration and lifecycle goals.
7. Run `mvn clean package`, inspect the JAR layout, and test `java -jar`.

**Common pitfall when switching from starter parent:** the Boot parent also provided Java release defaults, encoding, plugin management, and resource filtering. When replacing the parent, you need more than just `repackage`; verify that compiler/test/resource plugins remain appropriate. Do not assume importing the BOM preserves all previous build behavior.

If the corporate parent already configures an execution ID `repackage`, the child POM can use **the same ID** to customize it via Maven inheritance rules. Adding a different ID while both executions run risks processing the archive twice. Base conclusions on the effective POM and logs.

## 12. Multi-Module Projects: Binding on the Right Module

Suppose:

~~~text
my-platform/              packaging=pom
├── shared-utils/         packaging=jar  (library)
├── business-domain/      packaging=jar  (library)
└── web-service/          packaging=jar  (Spring Boot application)
~~~

Rules to follow:

- **Root aggregator** with `pom` packaging does not build an application source JAR via `jar:jar`; do not blindly bind `repackage` at the root.
- **Library modules** should remain plain JARs so other modules can consume classes in standard classpath layout.
- **Application modules** with `main()` deployed via `java -jar` are the ones needing executable archives and `repackage`.
- **Corporate parent/`pluginManagement`** can manage the plugin version centrally; activate the goal only in runnable modules.
- When running the Maven reactor from root, check which module creates the Boot executable; do not assume every `.jar` output is an application.

Practical point: inside a Spring Boot executable JAR, application classes sit under `BOOT-INF/classes`, not the standard Maven library JAR layout. Replacing a library's main artifact with a Boot executable JAR can prevent downstream library consumers from finding its classes.

## 13. Keeping a Regular JAR and Producing an Additional Executable JAR via Classifier

By default, `spring-boot:repackage` **replaces the main artifact** with the executable JAR and keeps the original as a `.jar.original` file.

If you genuinely need both a plain JAR usable as a library **and** an executable JAR for deployment, configure a classifier on the executable. **Replace** the Boot plugin declaration in Section 6 with:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

When no source artifact already carries the `exec` classifier, the typical output is:

~~~text
target/boot-no-parent-1.0.0.jar        # Regular JAR
target/boot-no-parent-1.0.0-exec.jar   # Executable Spring Boot JAR
~~~

Then the command to run the application is:

~~~bash
mvn clean package
java -jar target/boot-no-parent-1.0.0-exec.jar
~~~

**Technical note:** if another plugin already creates a JAR with the `exec` classifier, the Boot plugin may pick that classifier-matched artifact as the **source to repackage**. Check ordering and inputs whenever multiple archives are created in the same phase. The `attach` setting (default `true`) controls how the repackaged artifact is attached for install/deploy; with a classifier, the executable artifact can be attached alongside the plain JAR.

Usually it is cleaner to separate library modules and application modules when two artifacts serve different purposes. Even with a classifier, the core lesson remains **binding `repackage` to `package`**.

## 14. Variants and Boundaries to Watch

### 14.1. Setting the Main Class Manually

If there are multiple `main()` classes or the plugin cannot detect the entry point, add to the Spring Boot plugin configuration:

~~~xml
<configuration>
    <mainClass>com.example.demo.DemoApplication</mainClass>
</configuration>
~~~

This snippet goes **inside the plugin**, not as a standalone POM. Do not use a starter-parent property assuming it works identically without the parent; configuring `mainClass` directly in the Boot plugin is more explicit.

### 14.2. `layout=NONE` Does Not Produce a Standard Runnable Archive

The `repackage` goal supports layouts `JAR`, `WAR`, `ZIP`/`DIR`, and `NONE`. `NONE` can bundle dependencies without adding the bootstrap launcher, so it does not satisfy building a Spring Boot JAR runnable with `java -jar`. Do not use `NONE` when your goal is an executable JAR.

### 14.3. WAR Does Not Share the JAR Layout

If the project uses `<packaging>war</packaging>`, configure the WAR Plugin and servlet runtime accordingly. An executable WAR uses `WEB-INF/classes`, `WEB-INF/lib`, and possibly `WEB-INF/lib-provided`. The `BOOT-INF` checks for JARs do not apply verbatim to WARs.

### 14.4. `skip` and Dependency Excludes

If `repackage` has `skip=true` (from POM, profile, or command line), the build can succeed while skipping executable packaging. When excluding dependencies on the Boot plugin, confirm you are not stripping required runtime libraries. Do not assume classpath correctness solely from compile success.

### 14.5. Do Not Run `mvn package spring-boot:repackage` When Already Bound

Boot docs show `mvn package spring-boot:repackage` to run the goal directly after Maven builds the source archive. **With the POM taught in this lesson, the execution already binds `repackage` to `package`**, so the standard command is `mvn package` or `mvn clean package`. Appending the goal directly adds no quality guarantee and can repeat work.

### 14.6. Right Versions, Right Java, and Right Scopes

Keep the BOM, BOM-managed starter versions, and Boot Maven Plugin aligned on the same compatible line. Spring Boot 4.1.2 requires Java 17+ and Maven 3.6.3+. Java running Maven and Java used for compilation can differ if toolchains are configured; inspect `mvn -version` and compiler configuration to know the actual setup. The executable archive in production needs a Java runtime compatible with Boot, classes, and dependencies.

## 15. Common Errors and Root-Cause Tracing

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `mvn package` passes but produces only a plain JAR | `repackage` not bound, plugin only in `pluginManagement` | Inspect effective POM; place plugin in `build/plugins` and add execution |
| Maven reports missing Boot Maven Plugin version | Importing BOM does not manage plugin versions | Specify `<version>4.1.2</version>` or inherit from corporate `pluginManagement` |
| Log lacks `spring-boot:repackage` | Execution missing goal, disabled profile, wrong module, or skipped | Check `<goals>`, `<phase>`, and active profiles |
| `repackage` runs before `jar:jar` | Wrong execution/ordering in custom packaging setup | Build input archive first; declare Jar Plugin before Boot Plugin |
| Running `mvn spring-boot:repackage` standalone fails | Goal has no input JAR/WAR yet | Bind the goal and run `mvn clean package` |
| `Unable to find main class` | No valid `main`, multiple `main`s, or not compiled | Check Java entry point, `target/classes`, and `mainClass` |
| `no main manifest attribute` | Running plain JAR, `.jar.original`, or not repackaged | Check `jar tf`, manifest, and the filename executed |
| `ClassNotFoundException` at runtime | Missing runtime dependency or picked plain JAR | Check `BOOT-INF/lib`, scopes, exclusions, and archive |
| `BOOT-INF` missing despite green build | Goal skipped, different layout, or inspecting a stale/wrong archive | Run `mvn clean package`, inspect log/repackage configuration |
| `repackage` runs twice | Corporate parent already defines execution; child added another ID | Inspect effective POM and merge executions |
| Multi-module root fails complaining no source artifact | `repackage` bound on `pom` packaging | Bind only in `jar`/`war` application modules |
| Another module cannot import classes from Boot JAR | Used executable JAR as a library dependency | Keep plain library JAR or split modules |
| CI cannot find executable | `classifier=exec` or `finalName` changed output path but CI wasn't updated | Cross-check output path, version, and classifier |
| Unit tests do not run | Surefire too old or broken test discovery | Pin suitable Surefire version, check `target/surefire-reports`; never treat 0 tests as PASS |
| Maven build passes but Java 17 runtime fails to load classes | Mismatched compiler release or dependency Java bytecode level | Check `maven.compiler.release`, JDK, and class file versions |

A failure at `compile`, `test`, or dependency resolution **should not be fixed by tweaking `repackage` configuration**. Identify the first failing phase, inspect its inputs/outputs, and rerun the proper lifecycle.

## 16. Mandatory Verification Workflow for a POM-Editing Pull Request

Use this table for review:

| Criterion | Expected Evidence | PASS When |
| --- | --- | --- |
| Dependency management | `mvn dependency:tree` | Starter/runtime dependencies resolve properly |
| Plugin configuration | `mvn help:effective-pom` | Plugin version is right and `repackage` execution is at `package` |
| Phase ordering | `mvn clean package` log | `jar:jar` runs before `spring-boot:repackage` |
| Compile and tests | Class files and Surefire report | Zero errors and required tests are actually discovered |
| Executable layout | `jar tf target/...jar` | Has `BOOT-INF/classes`, `BOOT-INF/lib`, Boot loader |
| Manifest | `META-INF/MANIFEST.MF` | `Main-Class` is launcher; `Start-Class` is main class |
| Startup | `java -jar target/...jar` | App starts on target JDK |
| HTTP smoke test | `curl` to `/hello` | HTTP 200 and expected body |
| Multi-module / classifier | Artifact path, classifier, reactor log | Only application modules repackaged, library JARs intact |

**Why multi-layer checks?** `BUILD SUCCESS` proves that the goals Maven executed completed under the active config. It does not automatically prove that `repackage` was bound, that the chosen JAR is executable, or that the app works at runtime. Cross-check the actual output.

## 17. Comprehension Check Exercises

**1.** A project imports `spring-boot-dependencies` and declares `spring-boot-starter-webmvc`. Why might `mvn package` still build only a plain JAR?

*Answer:* The BOM only manages dependency versions; the starter only declares dependencies. Neither automatically binds the Boot Maven Plugin to the `package` phase.

**2.** A project does not use starter parent, yet `build/plugins` lists Boot Maven Plugin version `4.1.2`. Is `<executions>` still needed?

*Answer:* Yes, unless an equivalent execution is already inherited from another parent. Maven must be told to run the `repackage` goal as part of the lifecycle.

**3.** What is the purpose of `<phase>package</phase>` in an execution? Is writing it explicitly mandatory?

*Answer:* It specifies when the goal runs. Because `repackage` defaults to the `package` phase, omitting `phase` works in standard goal execution; writing it explicitly helps readers and CI reviewers inspect it easily.

**4.** If you run `mvn spring-boot:repackage` on a project with no source JAR yet, what can happen?

*Answer:* The goal lacks an archive to repackage and can fail. Run up through `package` so the source JAR/WAR is built first.

**5.** There is a JAR in `target` and Maven reports `BUILD SUCCESS`. Does that prove `repackage` ran properly?

*Answer:* Not yet. Check the goal log, effective POM, Boot layout, manifest, and test with `java -jar`.

**6.** In a corporate-parent project with modules `common` and `service`, where should `repackage` be bound?

*Answer:* In the `service` module that needs an executable; keep `common` as a plain library JAR.

**7.** Why should an executable Boot JAR not be used as a dependency for another library module?

*Answer:* Classes reside under `BOOT-INF/classes`, unlike a standard library JAR's classpath layout. Separate modules or preserve a plain JAR using a classifier.

**8.** When adding `<classifier>exec</classifier>`, which run command is appropriate?

*Answer:* `java -jar target/boot-no-parent-1.0.0-exec.jar`, provided that output is indeed the executable artifact.

**9.** When dropping starter parent in favor of a corporate parent, besides `repackage`, what else must be verified?

*Answer:* Java compiler release, encoding, resource filtering, compiler/resources/test/jar plugin versions, dependency versions, and inherited configuration in the effective POM.

**10.** If the Boot plugin appears twice in build logs, what is the first thing to inspect?

*Answer:* `mvn help:effective-pom` to inspect inherited executions, their IDs, and whether the child POM added a new execution alongside an existing `repackage` execution.

## 18. Self-Check Adoption Checklist

- [ ] Application module POM uses the right `<packaging>jar</packaging>` or `war`.
- [ ] Does not rely on starter parent when the project intentionally uses another parent.
- [ ] Imports the `spring-boot-dependencies` BOM to manage dependency versions.
- [ ] Spring Boot Maven Plugin has the right version and is activated in `build/plugins`.
- [ ] Has a `repackage` execution with goal `repackage` and phase `package` (explicit or via default phase).
- [ ] No unintended duplicate `repackage` executions from parent or profiles.
- [ ] Jar Plugin/source archive runs before Boot `repackage`.
- [ ] Java release, resources, and Surefire do not rely on defaults lost when dropping the parent.
- [ ] `mvn clean package` runs required tests and produces an executable archive.
- [ ] `jar tf` shows Boot layout; manifest has launcher `Main-Class` and app `Start-Class`.
- [ ] `java -jar` starts cleanly and HTTP smoke test returns the expected content.
- [ ] CI picks the right artifact when `classifier`/`finalName` is used.
- [ ] In multi-module builds, only application modules are repackaged.

**Memory aid:** *Starters pick libraries, the BOM manages dependency versions, and the Maven build plugin + execution binds `repackage` to the `package` phase.* Without the starter parent, **explicitly configuring the execution** is the decisive step for `mvn clean package` to produce a Spring Boot executable JAR.

## 19. Official References

1. [Spring Boot — Create an Executable JAR with Maven](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot Maven Plugin — Using the Plugin; without the Parent POM](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
4. [Spring Boot — Launching Executable JARs](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
5. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
6. [Apache Maven — Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
7. [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
8. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)