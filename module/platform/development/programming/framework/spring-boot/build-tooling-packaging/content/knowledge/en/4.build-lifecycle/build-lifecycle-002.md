# The Maven Build Lifecycle: validate, compile, test, package, verify, install, and deploy

In a Spring Boot project using **Maven**, the words `validate`, `compile`, `test`, `package`, `verify`, `install`, and `deploy` are **phases** of the *default build lifecycle*. They are ordered milestones; Maven performs the actual work through **plugin goals** bound to each phase. Understanding this helps you know which command only compiles, which runs tests, which produces an executable JAR, and which publishes artifacts for other projects.

> Scope: this lesson accurately explains the **Maven lifecycle in Spring Boot**, then compares it conceptually with Gradle. Gradle has its own task mechanism; it does not have an identical Maven phase sequence.

## 1. Distinguishing lifecycle, phase, plugin, and goal

- **Lifecycle** is a build process defined by Maven. Maven has three built-in lifecycles: `default` (build/distribute artifacts), `clean` (remove outputs), and `site` (generate site documentation).
- **Phase** is a milestone within a lifecycle, such as `test` or `package`. A phase name itself contains no algorithm to compile or run tests.
- **Plugin** is an extension that provides specific tasks, such as `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-jar-plugin`, or `spring-boot-maven-plugin`.
- **Goal** is an operation of a plugin, such as `compiler:compile`, `surefire:test`, `jar:jar`, `spring-boot:repackage`.
- **Binding** is the association of a goal with a phase. Default bindings depend on the POM's `<packaging>` (`jar`, `war`, `pom`, …); plugins/parent POMs can also add or adjust bindings.

For example, in a `jar` project, when running `mvn compile`, Maven proceeds through the necessary phases up to `compile`; at the `compile` phase, the compiler plugin typically executes the Java compilation goal. The command `mvn compiler:compile` invokes a goal directly; it is not equivalent to the full `mvn compile` process because it may skip earlier resource/source preparation phases bound beforehand.

Two core rules:

1. **Invoke the final phase you want to reach:** `mvn verify` automatically goes through the phases before `verify`. There is no need to type `mvn validate compile test package verify`.
2. **A phase running does not mean every kind of check is configured:** `verify` only performs actual checks if the corresponding plugin goals are bound; `package` only produces an executable Boot JAR if Spring Boot packaging is configured properly.

## 2. Order of the seven phases and typical outputs

~~~text
                      DEFAULT LIFECYCLE (MAVEN)
                               |
       validate -> compile -> test -> package -> verify -> install -> deploy
          |          |         |        |         |         |         |
       Valid POM  .class   unit test  JAR/WAR   check IT   Maven    Remote
                                         |        & QA    local repo artifact repo
                                         v
                                Spring Boot repackage
                                if plugin is bound
~~~

This is an **abbreviated diagram**, not an exhaustive list of every phase. Maven also has intermediate milestones such as `process-resources`, `test-compile`, `pre-integration-test`, `integration-test`, and `post-integration-test`. When running `mvn verify`, Maven passes through those intermediate milestones in exact order as well.

| Phase | What does Maven aim to do? | Common work when plugins are bound | Is there a usable artifact yet? |
| --- | --- | --- | --- |
| `validate` | Confirm project metadata/structure is sufficient to build | Validate POM and configuration prerequisites; may add Enforcer | No |
| `compile` | Compile application code | Process resources, `compiler:compile` → `target/classes` | Not packaged yet |
| `test` | Compile and run unit tests | `compiler:testCompile`, `surefire:test` → reports in `target/surefire-reports` | Not packaged yet |
| `package` | Package the distributable | `jar:jar`/`war:war`; with Boot, adds `spring-boot:repackage` | Usually produces JAR/WAR |
| `verify` | Verify the artifact and additional test results | Check integration test results via Failsafe, quality checks if configured | Yes; adds verification evidence |
| `install` | Put the artifact into the Maven repository **on the current machine** | `install:install` | Yes, for other local projects to use |
| `deploy` | Publish the artifact to a **remote repository** | `deploy:deploy` | Yes, for CI/other teams/projects to fetch |

`validate` does not mean Maven automatically checks all business logic. `verify` does not mean every project automatically runs integration tests, coverage, or security scans. The actual value of each milestone depends on the **POM, packaging, plugin bindings, and active profiles**.

## 3. What does each phase do—and not do?

### 3.1. `validate` — check initial conditions

~~~bash
mvn validate
~~~

Maven loads/reads the required configuration, validates the project model, and proceeds to the `validate` phase. Custom plugins or `maven-enforcer-plugin` can check Java/Maven versions and policies if configured. This is the point to catch missing POM information, invalid configurations, or violated project rules early.

**Do not infer:** that `mvn validate` has run unit tests or created a JAR; nor does it by default check business rules, security, or coding style.

### 3.2. `compile` — compile production code

~~~bash
mvn compile
~~~

For a Java `jar` project, standard goals typically process resources and then use the compiler to turn `src/main/java` into `target/classes`. Maven resolves compile classpath dependencies, while the **JDK** provides the actual compiler.

Example `src/main/java/com/example/demo/MessageService.java`:

~~~java
package com.example.demo;

public class MessageService {
    public String message() {
        return "Hello Maven lifecycle";
    }
}
~~~

After `mvn compile`, this class is typically located at `target/classes/com/example/demo/MessageService.class`. This is **bytecode**, not yet a distributable JAR file. `compile` does not reach `test-compile` and `test`, so do not treat `mvn compile` as a successful test result.

### 3.3. `test` — unit testing and preparation steps

~~~bash
mvn test
~~~

Maven executes the preceding phases, processes test resources, compiles code in `src/test/java`, and then typically invokes `maven-surefire-plugin` to run unit tests. With an appropriate JUnit Jupiter setup, a test class looks like:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello Maven lifecycle", new MessageService().message());
    }
}
~~~

The class name `MessageServiceTest` matches Surefire's default naming pattern. The test verifies `MessageService` behavior without starting a server. If tests fail, the build normally stops before `package`.

Note that `mvn test` is **not equivalent** to `mvn -DskipTests package`. In the second case, Maven may still compile test sources but skips running the tests; `-Dmaven.test.skip=true` further instructs supported plugins to skip test compilation. Do not use skip flags to prove release quality.

### 3.4. `package` — create the artifact

~~~bash
mvn package
~~~

With `<packaging>jar</packaging>`, Maven creates a JAR file in `target/` based on the artifact name/version. If a Spring Boot project has `spring-boot-maven-plugin` configured to run `repackage`, this goal **repackages the created archive** into an executable Spring Boot JAR that can be run with `java -jar` and carries runtime dependencies according to Boot's packaging layout.

Distinction:

- **Plain JAR:** a standard Java archive; not guaranteed to have a launcher, `Main-Class`, or enough dependencies to run standalone.
- **Executable Spring Boot JAR:** has the Boot structure (such as `BOOT-INF/classes` and `BOOT-INF/lib`) along with a launcher. When built properly, it can be started with `java -jar`.
- **WAR:** used when choosing `war` packaging and suitable configuration; follows servlet container/deployment conventions.

`package` runs after unit tests in the default lifecycle. **A successfully created JAR does not guarantee the application will connect to a database, open a port, or work properly in production.**

### 3.5. `verify` — verify build results and integration tests

~~~bash
mvn verify
~~~

This is a milestone after `package`. Before `verify` are `pre-integration-test`, `integration-test`, and `post-integration-test`. If Failsafe is configured, integration tests execute at `integration-test` and results are verified at `verify`, allowing environment cleanup in `post-integration-test` to run before the build fails on test errors.

Common points of confusion:

- **Surefire** typically runs unit tests at `test`.
- **Failsafe** typically runs integration tests at `integration-test` and checks results at `verify`, **but must be declared/bound** appropriately.
- Invoking `mvn integration-test` directly may skip `post-integration-test`/`verify`, leaving cleanup or result verification incomplete. When a project has an integration test lifecycle, **prefer `mvn verify`**.
- `mvn verify` does not automatically create integration tests, quality gates, or coverage thresholds. Those rules come from declared plugins/configurations.

If a project has not declared any specific goals for integration tests/verify, `mvn package` and `mvn verify` may have very similar practical outcomes. Do not conclude from that that the two phases are the same concept.

### 3.6. `install` — install the artifact into the local repository

~~~bash
mvn install
~~~

Maven runs the earlier phases, then installs the artifact, POM, and related metadata into the **local Maven repository**. By default, the repository is located at `~/.m2/repository` on many environments; the location can be changed via Maven configuration.

Suppose a project has Maven coordinates:

~~~text
groupId:    com.example
artifactId: lifecycle-demo
version:    1.0.0
packaging:  jar
~~~

A successfully installed artifact has a path like:

~~~text
~/.m2/repository/com/example/lifecycle-demo/1.0.0/lifecycle-demo-1.0.0.jar
~~~

Another project in the **same Maven/repository environment** can declare the dependency `com.example:lifecycle-demo:1.0.0` if the artifact is suitable as a dependency. With an executable Boot JAR, using it like a normal Java library is usually **not the right choice** because the executable archive structure differs from a plain library JAR; design a separate library module when sharing APIs/code.

`install` does **not** send files to a team server, run Spring Boot, or create a container deployment.

### 3.7. `deploy` — push the artifact to a remote Maven repository

~~~bash
mvn deploy
~~~

After the preceding phases succeed, the Maven deploy plugin pushes the artifact along with its POM/metadata to a **remote artifact repository** such as Nexus, Artifactory, or an equivalent service, according to publish configuration. This usually requires `distributionManagement` in the POM or equivalent configuration, and credentials matching the repository ID in `settings.xml` or CI secret mechanisms.

**Important: Maven `deploy` does not mean "deploy and start Spring Boot in production".** It publishes the build output for other systems to download. Delivering a JAR/container image to a VM, Kubernetes, or cloud platform and starting/rolling out the service is a **separate application deployment step**, performed by CD pipelines, Docker/Kubernetes, or operations tools.

`mvn deploy` can fail if the repository URL, credentials, publish permissions, network, or version policy (e.g., disallowing release overwrites) are missing or invalid. Only run deploy when the genuine intent is to publish the artifact to a shared repository.

## 4. Which phases run when you invoke a phase?

| Command | Final milestone of default lifecycle | Typical effect |
| --- | --- | --- |
| `mvn validate` | `validate` | Validate configuration; not yet compiled |
| `mvn compile` | `compile` | Compile main code; tests not run |
| `mvn test` | `test` | Compile main/test and run unit tests |
| `mvn package` | `package` | Run unit tests then create archive |
| `mvn verify` | `verify` | Package, integration phases, and configured verify steps |
| `mvn install` | `install` | Verify then add artifact to local repo |
| `mvn deploy` | `deploy` | Install then publish to remote artifact repo |
| `mvn clean verify` | `clean` first, then `verify` | Remove old output before building fresh up to verify |

**Note on `clean`:** it belongs to the independent *clean lifecycle*. `mvn package` does not delete the `target` directory by default. `mvn clean package` runs the `clean` phase and then runs the default lifecycle up to `package`. This is why CI often uses a clean build to reduce interference from leftover outputs of previous builds.

**Note on order:** Maven executes phases in standard order; there is no need to type the entire chain. A phase can have multiple goals, and some phases can have no goals bound. Directly invoked plugin goals like `mvn spring-boot:run` or `mvn surefire:test` are a different type of command from invoking a phase: prior preparation behavior depends on the goal and configuration, and should not be assumed to represent the full lifecycle.

## 5. Practice lab: Maven packaging a Spring Boot JAR

This example uses **Java 21**, **Maven 3.9.x**, and **Spring Boot 3.3.5** to pin demonstration behavior; these versions are chosen for the lab, not claimed to be the latest releases. Maven must have a compatible JDK and repository access to download dependencies.

Create the structure:

~~~text
lifecycle-demo/
  pom.xml
  src/
    main/java/com/example/demo/
      DemoApplication.java
      MessageService.java
    test/java/com/example/demo/
      MessageServiceTest.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println(new MessageService().message());
    }
}
~~~

**src/main/java/com/example/demo/MessageService.java**

~~~java
package com.example.demo;

public class MessageService {
    public String message() {
        return "Hello Maven lifecycle";
    }
}
~~~

**src/test/java/com/example/demo/MessageServiceTest.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello Maven lifecycle", new MessageService().message());
    }
}
~~~

`spring-boot-starter-parent` provides conventions and plugin management; `spring-boot-maven-plugin` declared in `build.plugins` uses the `repackage` configuration prepared by the parent. `spring-boot-starter-test` provides JUnit Jupiter libraries in the test scope. You do not need to manually specify each starter's version in this sample.

From the `lifecycle-demo` directory, run sequentially:

~~~bash
java --version
mvn --version
mvn clean test
mvn package
mvn verify
~~~

With the code and dependencies above, `MessageServiceTest` will run and pass. Log line counts, timings, and Maven report formatting vary by environment; do not copy those lines as fixed stdout.

Inspect the artifact after `package`/`verify`:

~~~bash
jar tf target/lifecycle-demo-1.0.0.jar
java -jar target/lifecycle-demo-1.0.0.jar
~~~

The `jar tf` command lists the archive contents (look for `BOOT-INF/classes` and `BOOT-INF/lib`). In the startup log when running the JAR, there will be a line:

~~~text
Hello Maven lifecycle
~~~

That is the line emitted by `System.out.println`; other Spring Boot log lines are not pinned in this example. Because the sample only uses `spring-boot-starter`, it **does not create an HTTP server**. The purpose is to observe the differences between **compile**, **unit test**, **creating an executable JAR**, and **running the artifact**.

If the project has a Maven Wrapper, use `./mvnw` on Linux/macOS or `mvnw.cmd` on Windows instead of `mvn` in the commands above. The Wrapper uses the Maven version configured by the project.

### Dissecting what happens when running `mvn package`

1. Maven reads the POM, parent, dependencies, and plugin bindings.
2. Phases up to `compile` create `target/classes` from code in `src/main/java`.
3. Phases up to `test` compile `MessageServiceTest` and then Surefire runs the test; a failure can stop the build.
4. At `package`, the JAR plugin creates an archive; the Spring Boot Maven plugin runs `repackage` per parent/plugin configuration to create an executable JAR.
5. Maven stops at `package`, **without running `verify`, `install`, or `deploy`** unless there is another independent invocation outside the sequence described.

`java -jar ...` is a **runtime** command, not a Maven phase. Once the JAR is ready, the server running the application does not necessarily need Maven.

## 6. When does `verify` differ from `package`? Integration test example with Failsafe

The lab in section 5 has unit tests, so `mvn package` and `mvn verify` both run `MessageServiceTest`. If you want Maven to actually execute integration tests in separate phases, you need to configure Failsafe.

Add the following plugin inside `<build><plugins> ... </plugins></build>` of the POM (keep the existing Spring Boot plugin):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Create test **src/test/java/com/example/demo/ApplicationIT.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationIT {
    @Test
    void springApplicationContextStarts() {
        // Succeeds when the Spring Boot application context is initialized.
    }
}
~~~

`@SpringBootTest` initializes a real application context rather than just calling a Java method; this is a **simple integration/smoke test of application configuration**, not a database or HTTP integration test. The name `ApplicationIT` matches Failsafe's detection convention, while `MessageServiceTest` still runs via Surefire. With the dependencies and plugins in the sample POM, the test can initialize the context without needing a web server.

Execute:

~~~bash
mvn clean package
mvn clean verify
~~~

With this configuration:

- `package` runs **unit tests** and then creates the JAR; it has not reached `integration-test`, so it does not run `ApplicationIT` via Failsafe.
- `verify` passes through `integration-test`, Failsafe runs `ApplicationIT`, and then the `failsafe:verify` goal checks the result. If the test fails, `verify` reports a build failure under default configuration.
- Corresponding reports are usually in `target/surefire-reports` and `target/failsafe-reports`. To know clearly which tests ran, inspect the goal logs and actual reports instead of just reading phase names.

For integration tests that require starting a database/container: you can bind setup tasks to `pre-integration-test`, run tests at `integration-test`, clean up the environment at `post-integration-test`, and use `verify` to decide pass/fail. Do not invoke `mvn integration-test` directly as the final CI command because it may skip cleanup and verification.

## 7. Artifact publishing mechanism: install vs deploy vs running the application

Three things are easily lumped together as "deploy", yet their outputs and destinations differ:

~~~text
mvn verify
   -> Proves the build satisfies the configured checks
   -> artifact remains in target/

mvn install
   -> Steps up to verify + stores the artifact/POM in the local Maven repository
   -> Other builds sharing the local repo can resolve the artifact

mvn deploy
   -> Steps up to install + uploads the artifact/POM to a remote Maven repository
   -> CI, other teams, or CD pipelines can download the artifact

Application deployment (CD)
   -> Downloads artifact or builds image -> delivers to runtime -> startup/rollout
   -> Environment configuration, service, network, health check
~~~

For `mvn deploy` to work, publishing repositories are typically configured (illustrative, **placeholder URL**):

~~~xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.invalid/maven-releases</url>
    </repository>
</distributionManagement>
~~~

And credentials are configured in Maven's `settings.xml` or CI secrets matching the ID `team-releases`; do not put passwords/tokens directly in the POM. If publishing SNAPSHOTs, appropriate policies and `snapshotRepository` are required. The sample configuration above **only explains the mechanism**, not a real publishable repository.

When you only need to check the project before merging, `mvn clean verify` is commonly used. When another project on the same machine needs to use the newly built dependency, use `mvn install`. When releasing artifacts to a shared repository, execute `mvn deploy` according to established CI/release permissions and workflows.

**With Spring Boot:** the application runs from the executable JAR in `target/`, and the CD system can use that same JAR to build an image/deploy the service. Maven does not automatically create a Kubernetes Deployment or open application ports just because `deploy` succeeded. On the other hand, if a project uses Gradle, publishing steps have corresponding tasks based on configured plugins; task names and ordering should not be copied verbatim from Maven.

## 8. A Maven phase is not a Gradle task: mapping at the right level

In a Spring Boot module using **Gradle**, the mechanism is a task graph and task dependencies. It does not have Maven's exact `validate → ... → deploy` phase sequence.

| Objective | Commonly used in Maven | Commonly used in Gradle when appropriate plugins are applied |
| --- | --- | --- |
| Compile Java sources | `mvn compile` | `./gradlew classes` or `./gradlew compileJava` |
| Run unit tests | `mvn test` | `./gradlew test` |
| Verify and build | `mvn verify` | `./gradlew build` (usually includes `check` and `assemble`) |
| Create executable Spring Boot JAR | `mvn package` with Boot `repackage` | `./gradlew bootJar` |
| Publish to local Maven repo | `mvn install` | `./gradlew publishToMavenLocal` with `maven-publish` |
| Publish to remote artifact repo | `mvn deploy` | `./gradlew publish` when repositories/publications are configured |

This is an **intent mapping**, not a 100% equivalence guarantee. For instance, `gradlew build` does not automatically enable all integration test tasks if the project has not wired them into `check`/`build`; and the `publish` task is only meaningful when declared by a publishing plugin. The Spring Boot Gradle plugin provides tasks like `bootJar`, whereas the Spring Boot Maven plugin uses goals like `repackage`.

## 9. Diagnosing issues by actual phase

| Symptom | Check first | Troubleshooting hint |
| --- | --- | --- |
| Maven cannot read project/POM | `validate`/project model | Check XML, parent, repository config, whether plugins resolve |
| `invalid target release: 21` | `compile` and JDK | `mvn --version`, JDK used by Maven/Compiler, `<java.version>` or compiler release |
| `cannot find symbol` | `compile` | Source errors, imports, compile classpath dependencies; unrelated to deploy |
| Unit test fails | `test` / Surefire | Check `target/surefire-reports`, test name, stack trace |
| `mvn package` PASSES but no executable JAR | `package` / Boot plugin | Check `spring-boot-maven-plugin`, `repackage` binding, packaging, filenames in `target` |
| `mvn package` PASSES, `mvn verify` FAILS | `integration-test`/`verify` | Check configured Failsafe/quality goals and specific reports |
| `mvn install` FAILS | `install` / local repository | Check write permissions, local repository path, disk space, artifact metadata |
| `mvn deploy` FAILS with 401/403 or missing repository | `deploy` / publishing | Check repository ID/URL, `settings.xml`, credentials, publish permissions |
| `mvn deploy` PASSES but server not running new version | Application deployment step **outside Maven** | Check CD pipeline, image/tag, rollout, runtime config |
| `java -jar` fails on server | JVM/runtime/dependencies | Java version, JAR structure, environment variables, memory, database, port |

A quick way to read logs: find the last **plugin:goal** that ran before the error. For example, `maven-compiler-plugin:compile` points to build/Java; `maven-surefire-plugin:test` points to unit tests; `spring-boot-maven-plugin:repackage` points to packaging; `maven-deploy-plugin:deploy` points to artifact publishing. The line `BUILD FAILURE` states that the build failed, but does not by itself identify the category of root cause.

### Ways to skip tests you need to understand clearly

- `mvn -DskipTests package`: typically compiles tests but skips running Surefire/Failsafe tests; do not use to claim tests PASS.
- `mvn -Dmaven.test.skip=true package`: for plugins that support it, also skips compiling test sources.
- `mvn -Dtest=MessageServiceTest test`: runs a specific test via Surefire during an investigation; it does not prove the entire test suite PASSES.

Skipping tests does not fix errors in `compile`/`repackage` and cannot replace `verify` in a controlled release process.

## 10. Self-check exercise for each milestone's output

With the sample project:

1. Run `mvn clean compile`, inspect `target/classes`, and confirm no distributable JAR is needed yet.
2. Run `mvn test`, observe `target/test-classes` and Surefire reports; intentionally make an assertion fail to observe failure in the test phase, then fix it back.
3. Run `mvn package`, inspect `target/lifecycle-demo-1.0.0.jar` and the `jar tf` command; explain the role of `repackage`.
4. Configure Failsafe and `ApplicationIT` then run `mvn verify`; compare with `package`.
5. Run `mvn install` if you need to share the artifact in the local Maven repository, then locate the path by `groupId:artifactId:version`.
6. **Only in an authorized publishing environment**, try `mvn deploy` with a valid remote repository; confirm the artifact is published to the repository, then describe the separate CD step to run Spring Boot on a server.

Three end-of-lesson self-check questions:

- **Why does `mvn package` still run unit tests?** Because Maven executes phases preceding `package`, including `test`.
- **Why can `mvn verify` run additional integration tests?** Because there are integration-test phases between `package` and `verify`, if bound to Failsafe/corresponding tasks.
- **Why did `mvn deploy` succeed while users do not yet see the new feature?** Because Maven only publishes the artifact to a remote repository; running/rolling out the application is the responsibility of the runtime/CD deployment step.

## Official documentation for reference

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): the three lifecycles, phases, and plugin bindings.
- [Apache Maven — Running Maven](https://maven.apache.org/run.html): phase/goal command syntax and common milestones.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): running integration tests and verifying at `verify`.
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): the `repackage` goal, executable JAR/WAR, and interaction with Maven package.
