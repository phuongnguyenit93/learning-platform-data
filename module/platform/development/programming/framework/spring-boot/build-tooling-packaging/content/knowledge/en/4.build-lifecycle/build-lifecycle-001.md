# Maven's Phase and Goal Model

A command like `mvn clean verify` looks short, but underneath Maven performs many tasks: deleting old outputs, processing resources, compiling Java, running unit tests, creating a JAR, running additional checks, and verifying quality. To read logs accurately or design a Spring Boot pipeline, you need to distinguish **lifecycle**, **phase**, **plugin**, **goal**, and **execution binding**. This is Maven's task orchestration model, not just a list of commands.

**Learning objectives:** After this lesson, you can (1) explain what Maven runs when a phase is invoked; (2) distinguish a phase from a directly invoked goal; (3) identify which goal is bound to which phase via `pom.xml`; (4) understand how Spring Boot creates an executable JAR and how to include integration tests in `verify`; (5) choose the right Maven command for development, CI, and release.

## 1. Five foundational concepts

| Concept | Role | Example |
| --- | --- | --- |
| **Project/POM** | Describes artifact coordinates, packaging, dependencies, plugins, and build configuration | `pom.xml`, `groupId`, `artifactId`, `version` |
| **Lifecycle** | A standard sequence of stages to handle a major objective | `default`, `clean`, `site` |
| **Phase** | An ordered milestone in a lifecycle; a phase itself contains no executable code | `compile`, `test`, `package`, `verify` |
| **Plugin** | A component that implements specific build tasks | `maven-compiler-plugin`, `maven-surefire-plugin` |
| **Goal** | An executable task belonging to a plugin | `compiler:compile`, `surefire:test`, `spring-boot:repackage` |

Relationship:

```text
POM + packaging + configuration/inheritance
                |
                v
      Lifecycle: default
                |
                v
       Phase: compile
                |
                v
  Plugin goal: compiler:compile
                |
                v
     target/classes/*.class
```

**A lifecycle is a sequence; a phase is a point in the sequence; a goal is the actual work performed by a plugin.** A phase can have 0, 1, or multiple goals bound to it. When no goal is bound, Maven still passes through that phase, but there is no task to run.

**Common confusion:** `compile` in `mvn compile` is a **phase**; `compile` in `mvn compiler:compile` is a **goal** of the Compiler Plugin. The two commands are not equivalent in overall work: a phase triggers the goals bound to every phase from the start of the lifecycle up to `compile`, whereas invoking a goal directly usually requests only that goal (and any prerequisites/dependencies declared by the goal itself).

## 2. Maven has three independent built-in lifecycles

| Lifecycle | Typical phases | Purpose |
| --- | --- | --- |
| **default** | `validate` → `compile` → `test` → `package` → `verify` → `install` → `deploy` | Building, testing, and distributing the artifact |
| **clean** | `pre-clean` → `clean` → `post-clean` | Cleaning previous build outputs |
| **site** | `pre-site` → `site` → `post-site` → `site-deploy` | Generating and publishing Maven documentation sites |

The table above summarizes the phases of `default`; in practice there are also many intermediate phases such as `process-resources`, `test-compile`, and `integration-test`. The name **default** lifecycle does not mean Maven automatically executes every phase when you open a project. Maven only runs when given a phase/goal and stops at the requested phase.

`mvn clean` invokes the `clean` phase belonging to the **clean lifecycle**; it does not compile or test. `mvn site` invokes the `site` phase belonging to the **site lifecycle**; it does not automatically create an executable JAR. When running:

```bash
mvn clean verify
```

Maven executes two parts in order: it runs the clean lifecycle **up to the `clean` phase**, and then runs the default lifecycle **up to the `verify` phase**. `post-clean` does not run automatically just because you requested `clean`. Similarly, `mvn verify` does not automatically clean `target/` before building; if you want a clean build, explicitly specify `clean`.

## 3. Default lifecycle: invoking a phase pulls in all preceding phases

Diagram of the main milestones:

```text
validate → compile → test → package → verify → install → deploy
                     ^                ^
                     |                |
                 mvn test        mvn verify
```

The `mvn verify` command executes all phases before `verify` in exact order. It does **not** run `install` or `deploy`. Conversely, `mvn deploy` goes through both `install` and `verify` before publishing the artifact to a remote repository.

Important phases of `default` in order:

| Phase | Meaning | Common goal with `jar` packaging |
| --- | --- | --- |
| `validate` | Validate the project model and inputs | May have no default goal |
| `initialize` / `generate-sources` | Initialize build state, generate sources if plugins are configured | Project-dependent |
| `process-resources` | Copy/process `src/main/resources` | `resources:resources` |
| `compile` | Compile `src/main/java` | `compiler:compile` |
| `process-test-resources` | Process `src/test/resources` | `resources:testResources` |
| `test-compile` | Compile `src/test/java` | `compiler:testCompile` |
| `test` | Run unit tests according to test plugin rules | `surefire:test` |
| `prepare-package` | Prepare before packaging if a custom goal exists | Project-dependent |
| `package` | Create JAR/WAR; Spring Boot can repackage | `jar:jar`, `spring-boot:repackage` |
| `pre-integration-test` | Set up the integration test environment | Project-dependent |
| `integration-test` | Run configured integration tests | `failsafe:integration-test` if configured |
| `post-integration-test` | Clean up integration test resources | Project-dependent |
| `verify` | Verify integration test results and other quality gates | `failsafe:verify` if configured |
| `install` | Install the artifact into the local Maven repository | `install:install` |
| `deploy` | Push the artifact to a remote Maven repository | `deploy:deploy` |

The remaining intermediate phases include `process-sources`, `generate-resources`, `process-classes`, `generate-test-sources`, `process-test-sources`, and `process-test-classes`; they only do work if goals are bound to them. The table describes **typical default bindings**, and does not guarantee every goal is present in every project. Packaging type, parent POM, plugins, and executions can change the outcome.

Examples of choosing commands by objective:

| Command | How far will Maven go? | Not yet executed |
| --- | --- | --- |
| `mvn validate` | Stops at `validate` | Compile, test, package |
| `mvn test` | Through `test`, including compile + unit tests | Package, integration-test, verify |
| `mvn package` | Through `package`, including earlier phases | Failsafe integration tests in later phases |
| `mvn verify` | Through `verify` | Install and deploy |
| `mvn install` | Through `install` | Remote deploy |
| `mvn deploy` | Through `deploy` | Deploying the application to a server (that is a separate task) |

Calling `mvn compile test package` on one line is redundant: invoking the final phase `mvn package` already runs the earlier phases. For CI, `mvn clean verify` is usually a good starting point; any desired quality gates must actually be configured.

## 4. How are goals bound to phases?

Maven determines which goals will run from two main sources:

1. **Default bindings by project `packaging`.** For `jar`, Maven automatically binds `compiler:compile` to `compile`, `surefire:test` to `test`, `jar:jar` to `package`, along with the appropriate resources/install/deploy goals. For `war`, the `package` phase uses the WAR creation goal; for `pom`, the packaging model differs.
2. **Plugin executions declared or inherited in the POM.** Executions can bind additional goals to phases, configure their purpose, change parameters, or add runs. When multiple goals share a phase, default packaging bindings run before additional POM executions; POM executions follow the order of the configuration/effective model accordingly.

Example of an execution manually binding the Checkstyle Plugin goal to `verify`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-checkstyle-plugin</artifactId>
            <version>3.3.1</version>
            <executions>
                <execution>
                    <id>check-code-style</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

This is a **configuration snippet inserted into the `<project>` section of a POM**, not a standalone POM file. When `mvn verify` reaches `verify`, Maven runs the `checkstyle:check` goal according to this configuration. A `mvn test` invocation alone will not run that goal. Checkstyle requires a ruleset suitable for the project; the XML snippet illustrates the **binding mechanism**, and does not guarantee every codebase will pass default style checks.

In an execution, the `<goals>` element specifies the task; `<phase>` specifies when it runs. Some goals have a **default phase** declared by the plugin, so an execution may omit `<phase>`; however, to make it easy for readers to inspect, declare the phase explicitly when you need to control placement. `<id>` helps identify the execution in logs and when inheriting/overriding configuration.

### Plugin, pluginManagement, and dependencyManagement are different

- `<build><plugins>` activates/configures plugins in the current build; with a valid execution, the plugin runs at the bound phase.
- `<build><pluginManagement>` provides default versions/configurations for plugins when they are used; **having only `pluginManagement` usually does not trigger executions in child projects** if the plugin is not applied/has no corresponding binding.
- `<dependencies>` manages libraries used to compile/test/run the application. Adding `spring-boot-starter-web` does not mean Maven automatically knows how to build an executable Boot JAR.
- `<dependencyManagement>` manages dependency versions/attributes, not where plugin goals are controlled.
- `<parent>` and profiles can inject plugin configurations/executions from elsewhere. Therefore, only the **effective POM** shows the complete picture after inheritance and profile activation.

Do not declare the same plugin twice in `<build><plugins>` to run multiple goals; use multiple `<execution>` entries inside the same plugin instead.

## 5. Phase command and goal command: same name, different meaning

Common Maven CLI syntax:

```text
mvn [options] [phase...] [plugin-prefix:goal...]
```

Examples:

```bash
mvn compile
mvn compiler:compile
mvn dependency:tree
mvn clean package
mvn clean package dependency:tree
```

**`mvn compile`**: runs the default lifecycle up to `compile`, including `process-resources` and any goals bound to earlier phases. **`mvn compiler:compile`**: directly invokes a goal of the Compiler Plugin; it does not by default trigger all phases prior to `compile`. Therefore, direct goal invocation is usually appropriate for diagnostics or targeted operations, not as an arbitrary substitute for the lifecycle.

**`mvn dependency:tree`**: invokes the `tree` goal of the Maven Dependency Plugin to view the dependency tree; it is not a lifecycle phase. The shorthand `plugin-prefix:goal` is resolved by Maven to the corresponding plugin; the full form is `groupId:artifactId:version:goal` when exact plugin version control is needed.

**`mvn clean package dependency:tree`**: Maven executes `clean`, the default lifecycle up to `package`, and then invokes `dependency:tree`. The order of arguments on the command line matters. There is no need to explicitly call `test` before `package` because `package` already includes `test` in the lifecycle.

Note: some plugin goals themselves declare that they require a project, resolve dependencies, or fork/invoke a phase before running; do not assume *every* direct goal behaves identically. Read the goal documentation and effective POM to determine actual prerequisites.

## 6. Runnable example: Maven phases/goals in a Spring Boot project

Uses Java 17, Maven 3.9.x, and Spring Boot 3.3.13. Minimal files:

```text
maven-phase-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/maven/
    │   └── MavenPhaseApplication.java
    └── test/java/dev/example/maven/
        └── MavenPhaseApplicationTest.java
```

Create the complete `pom.xml`:

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
    <artifactId>maven-phase-demo</artifactId>
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

File `src/main/java/dev/example/maven/MavenPhaseApplication.java`:

```java
package dev.example.maven;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MavenPhaseApplication {
    public static void main(String[] args) {
        SpringApplication.run(MavenPhaseApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello Maven lifecycle";
    }
}
```

File `src/test/java/dev/example/maven/MavenPhaseApplicationTest.java`:

```java
package dev.example.maven;

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
class MavenPhaseApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHello() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Maven lifecycle"));
    }
}
```

Run the milestones independently (each command goes through the required phases):

```bash
mvn -version
mvn clean test
mvn clean package
mvn clean verify
```

On machines with Maven Wrapper, replace `mvn` with `./mvnw` (Windows uses `mvnw.cmd`). Each `clean` command deletes existing build outputs before running the next part. `mvn test` runs tests named with the `Test` suffix via Surefire; `mvn package` creates `target/maven-phase-demo-1.0.0.jar` if successful.

**Why can this JAR run with `java -jar`?** `spring-boot-starter-parent` manages the `repackage` execution and the Spring Boot Maven Plugin is declared in `<build><plugins>`. When `package` creates the original JAR, the `spring-boot:repackage` goal repackages the application with the Spring Boot loader and runtime dependencies. Without this configuration, a standard JAR created by `jar:jar` may not run on its own with `java -jar`.

```bash
java -jar target/maven-phase-demo-1.0.0.jar
```

In another terminal, once the application has started:

```bash
curl -s http://localhost:8080/hello
```

Expected HTTP response body, matching the controller and test:

```text
Hello Maven lifecycle
```

**Note:** `spring-boot:repackage` operates on an already-created JAR/WAR, so if invoked directly in a project without lifecycle binding, you must run `mvn package spring-boot:repackage`, not `spring-boot:repackage` on a directory that does not yet have an artifact. With the POM in this example, the execution is already bound to `package`, so `mvn package` alone is sufficient; do not invoke the `repackage` goal a second time.

## 7. Inserting integration tests into the lifecycle properly

Maven has the phases `pre-integration-test` → `integration-test` → `post-integration-test` → `verify`. **Phase names do not make integration tests appear automatically.** You must configure the corresponding plugin or test framework. In Maven, Surefire handles unit tests at `test` by default, while Failsafe is meant for integration tests and verifies results at `verify`.

Add the following plugin to the **same `<build><plugins>` list in the POM from section 6** (do not replace the Spring Boot plugin):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <executions>
        <execution>
            <id>integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Those two goals have corresponding default phases: `failsafe:integration-test` binds to `integration-test` and `failsafe:verify` binds to `verify`. Class names matching `*IT` are picked up by Failsafe under the default pattern. For example, create `src/test/java/dev/example/maven/MavenPhaseApplicationIT.java`:

```java
package dev.example.maven;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MavenPhaseApplicationIT {
    @Autowired
    private TestRestTemplate restTemplate;

    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttp() {
        ResponseEntity<String> response = restTemplate.getForEntity(
                "http://localhost:" + port + "/hello", String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello Maven lifecycle", response.getBody());
    }
}
```

Run:

```bash
mvn clean verify
```

Sequence: Surefire runs `MavenPhaseApplicationTest` at `test` → packaging at `package` → Failsafe runs `MavenPhaseApplicationIT` at `integration-test` → the `failsafe:verify` goal checks the results and fails the build if integration tests fail. Check the reports in `target/surefire-reports/` and `target/failsafe-reports/`. Failsafe is designed to record integration test failures first, allowing `post-integration-test` steps to clean up resources before failing the build at `verify`.

**Do not stop at `mvn integration-test` when you need a final pass/fail verdict.** When invoking only that phase, `post-integration-test` and `verify` have not run yet; the test environment may not have been released, and Failsafe's verification is incomplete. Choose `mvn verify`.

In real applications, integration tests that use databases/queues/containers require plugins or tools to provision and tear them down accordingly; adding Failsafe alone does not automatically start those services.

## 8. Reading logs to identify executing phases and goals

Maven typically prints goal lines like the following (abbreviated for illustration, **not a fixed log**):

```text
--- maven-resources-plugin:...:resources (...) @ maven-phase-demo ---
--- maven-compiler-plugin:...:compile (...) @ maven-phase-demo ---
--- maven-resources-plugin:...:testResources (...) @ maven-phase-demo ---
--- maven-compiler-plugin:...:testCompile (...) @ maven-phase-demo ---
--- maven-surefire-plugin:...:test (...) @ maven-phase-demo ---
--- maven-jar-plugin:...:jar (...) @ maven-phase-demo ---
--- spring-boot-maven-plugin:...:repackage (...) @ maven-phase-demo ---
--- maven-failsafe-plugin:...:integration-test (...) @ maven-phase-demo ---
--- maven-failsafe-plugin:...:verify (...) @ maven-phase-demo ---
BUILD SUCCESS
```

Each line indicates the **plugin**, **actual version** (written here as `...`), **goal**, **execution id**, and artifact/project. You know whether a goal actually ran from the logs and plugin reports, not by guessing from the phase name.

If you only run `mvn test`, the log stops before `jar:jar`/`repackage`. If Failsafe is not configured, the log will not contain `failsafe:*` even though `mvn verify` can still finish with `BUILD SUCCESS`. In a multi-module project, the log also includes each module's name and a `Reactor Summary`; a failure in one module can prevent dependent modules from running.

Tools for self-checking configuration:

```bash
mvn help:effective-pom
mvn help:active-profiles
mvn help:describe -Dplugin=compiler -Dgoal=compile -Ddetail
mvn dependency:tree
```

- `help:effective-pom`: view the POM after Maven merges parent, profiles, pluginManagement, and effective declarations; used to locate inherited `<executions>` or plugin versions.
- `help:active-profiles`: confirm which profiles are active.
- `help:describe`: read the description and parameters of a goal.
- `dependency:tree`: read the dependency graph. It does not directly show all goal bindings; combine effective POM with logs.

Do not share raw debug logs or effective settings if they contain internal URLs, tokens, or sensitive information.

## 9. How `packaging`, parent, and profiles affect build results

From `<packaging>jar</packaging>`, Maven selects the default goal binding set for JARs. Switching to `war` changes the goal in `package` and requires appropriate application/dependency configuration for a servlet container environment. `<packaging>pom</packaging>` is commonly used as a parent/aggregator POM; it does not automatically produce an application JAR.

Spring Boot typically has two packaging layers:

1. The Maven JAR Plugin creates the base JAR according to the lifecycle.
2. The Spring Boot Maven Plugin with the `repackage` goal repackages it into an executable JAR/WAR with the loader and runtime dependencies.

Adding a Spring Boot dependency **does not automatically invoke the `repackage` goal**. You must declare the plugin and corresponding execution/binding; with `spring-boot-starter-parent`, the `repackage` configuration is pre-provided and the plugin is declared as shown in the example above.

Profiles can enable/disable plugins, properties, dependencies, or repositories, so two commands using different profiles can trigger different sets of goals. For example:

```bash
mvn -Pci clean verify
```

Only use `-Pci` when the POM actually declares a `ci` profile or activates it through a valid mechanism. If a CI build must include additional quality gates, inspect `effective-pom` and logs with the exact profile to be sure the goals are bound.

## 10. Maven in multi-module projects

A root POM of type `pom` can declare `<modules>` and form a Maven reactor. Maven determines module order based on inter-module dependencies so they build in the right order. For example, a project with `common` and `web-app` depending on `common`:

```text
root-pom (packaging=pom)
├── common (packaging=jar)
└── web-app (packaging=jar, Spring Boot executable JAR)
```

Running from root:

```bash
mvn clean verify
mvn -pl :web-app -am verify
```

The first command applies the lifecycle to the modules in the reactor. The second selects the module with artifactId `web-app` and adds the reactor modules it depends on via `-am`, such as `common` (assuming the dependency relationship is accurate). Phases/goals are still evaluated per **each module's** POM and packaging, so not every module produces an executable Boot JAR. Selecting `-pl`/`-am` does not replace the need to properly publish/identify the target module's artifact.

## 11. Choosing phases as quality gates in CI and releases

A pragmatic Maven pipeline can break stages down as follows:

| Need | Command | Evidence required |
| --- | --- | --- |
| Fast development, Java/test checks | `mvn test` | Unit tests pass, compilation succeeds |
| Clean build and create artifact | `mvn clean package` | Properly named JAR/WAR, unit tests pass |
| Combined pre-release gate | `mvn clean verify` | Tests + integration tests + configured quality goals all pass |
| Install for local use by other modules/projects | `mvn install` | Artifact appears in the local Maven repository |
| Publish to a Maven repository | `mvn deploy` | Valid repository target, publish succeeds, traceable version |

`mvn install` is the **phase that installs the artifact into the local repository** (usually `~/.m2/repository`), not a command to install the application into the OS. `mvn deploy` is the **phase that uploads the artifact to a Maven repository**, not a command to roll out a Spring Boot service to Kubernetes/VMs.

For `deploy` to work with a remote repository, you must configure `<distributionManagement>` for the target repository and provide secure authentication via Maven settings/secret manager. Avoid hard-coding passwords/tokens in the POM. If the release target is an OCI image/registry or server/container runtime, add a separate publish and deploy workflow using the verified artifact/image digest.

**Options that skip checks and affect gates:**

- `-DskipTests` usually skips running Surefire tests while still compiling tests.
- `-Dmaven.test.skip=true` also skips compiling tests for test plugins that support this property.
- If you use those flags for diagnostic checks, do not treat the artifact as having passed quality gates. Release CI should run the full test policy.

Pin Maven, JDK, plugin, and dependency versions and use Maven Wrapper when available; builds must be traceable to the Git commit, build environment, and artifact version. A phase reporting `BUILD SUCCESS` only confirms that the **actually bound** goals succeeded; it does not prove that unconfigured checks were completed.

## 12. Common errors and how to find root causes

| Symptom | Why | How to handle |
| --- | --- | --- |
| `mvn compiler:compile` succeeds but `mvn compile` fails | The phase triggers additional resource processing/source generation or other goals | Inspect the log for the specific failing goal; fix that goal's configuration |
| `mvn package` still creates a JAR even though integration tests have not run | Failsafe is in a phase after `package` or is not bound | Configure Failsafe, run `mvn verify` |
| `mvn verify` succeeds but there is no Failsafe report | Missing Failsafe execution or tests do not match pattern | Check effective POM, `*IT` naming, and `target/failsafe-reports/` |
| Calling `mvn integration-test` as the final check | Skips `post-integration-test`/`verify` | Use `mvn verify` to clean up environment and confirm results |
| JAR is in `target` but `java -jar` reports missing main manifest/loader | Missing valid `repackage` goal | Declare Spring Boot Maven Plugin/execution, run `package`, and inspect manifest |
| Added plugin in `pluginManagement` but goal does not run | Plugin/execution is not activated in the actual build | Declare under `<build><plugins>` or configure the required binding |
| `mvn clean` deletes artifacts without recreating them | `clean` is a separate lifecycle | Invoke `mvn clean package` or `mvn clean verify` |
| `mvn deploy` does not put the service on the server | This phase publishes Maven artifacts | Create a separate application deployment stage |
| Local and CI builds run different goals | Maven/JDK, parent, profiles, properties, or plugin versions differ | Compare `mvn -version`, effective POM, active profiles, and logs |
| `mvn test -DskipTests` succeeds but tests did not run | Option disables test execution | Remove the flag, check actual test counts in the Surefire report |

## 13. Command-reading exercises and self-check

**Scenario A.** The goal is to compile and run unit tests, without needing a JAR yet. Choose `mvn test`. Maven automatically runs through `compile` and `test-compile` before executing the Surefire goal.

**Scenario B.** You want a Spring Boot JAR runnable with `java -jar`, without publishing. Choose `mvn clean package` with `spring-boot-maven-plugin` binding `repackage`. Inspect the files in `target/` and actually run the artifact.

**Scenario C.** Failsafe is configured and all checks are needed before release. Choose `mvn clean verify`. Do not choose `mvn integration-test` because it lacks the cleanup phase and final test verdict.

**Scenario D.** A developer says “I ran `mvn verify` and it succeeded, so integration tests definitely ran.” This claim is **false** if the POM has not bound the corresponding plugin. Read the effective POM, goal logs, and reports instead of inferring from the phase name.

**Scenario E.** Someone proposes `mvn deploy` to deploy an HTTP service to the staging environment. Distinguish carefully: this is the **Maven repository publish** phase. Running the application on staging requires a separate deployment workflow that consumes the published artifact.

**Rule of thumb:** *Invoke a phase* ⇒ Maven steps through the preceding phases of the **same lifecycle**, running bound goals. *Invoke a goal* ⇒ requests a specific plugin task. Actual results depend on `packaging`, parent/effective POM, profiles, plugin executions, and tool versions.

### Official documentation for reference

- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Running Apache Maven: https://maven.apache.org/run.html
- Maven — Guide to Configuring Plugins: https://maven.apache.org/guides/mini/guide-configuring-plugins.html
- Maven Surefire/Failsafe — Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html