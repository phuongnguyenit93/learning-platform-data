# Coordinating `spring-boot:start` and `spring-boot:stop` in the Maven Integration Test Lifecycle

## 1. Goal and Scenario

A unit test can call a Java method directly, but many **integration tests** must test a real Spring Boot application listening over HTTP, connected to required services, and returning responses over the network. If you only start the server manually before running tests, the CI process depends on manual steps, risks forgetting to shut down the app, and causes port conflicts across builds.

The **Spring Boot Maven Plugin** provides two goals specifically for this scenario:

- **`spring-boot:start`** launches the Spring Boot application in a **separate process** and **does not block Maven indefinitely** like the `spring-boot:run` goal does. Maven can proceed to execute tests while the app stays up.
- **`spring-boot:stop`** sends a shutdown request to the application previously started by `start`, using the plugin's **JMX** management mechanism.
- **Maven Failsafe Plugin** runs integration tests at `integration-test` and evaluates results at `verify`. Failsafe is designed to **defer failing the build for test assertions until the `verify` phase**, giving the `post-integration-test` phase a chance to run cleanup.

After this lesson, you will be able to:

1. Sequence `start → integration-test → stop → verify` properly in the Maven lifecycle.
2. Distinguish Maven phases, Spring Boot Maven Plugin goals, and Maven Failsafe Plugin goals.
3. Configure the **HTTP port** and **JMX port** independently, ensuring `start` and `stop` share the same JMX port.
4. Write a `pom.xml` and standalone Java 17 test that calls a real HTTP application in a Maven-managed process.
5. Run `mvn clean verify` and verify test reports, start/stop logs, endpoint availability during tests, and shutdown afterward.
6. Troubleshoot failing tests, undiscovered ITs, JMX port conflicts, timeouts, alternate parent configurations, skipping ITs, CI, and multi-module builds.
7. Understand cleanup limits: severe build/start/plugin errors can still prevent Maven from reaching the `stop` phase, so CI needs fallback cleanup when necessary.

**Example:** Spring Boot 4.1.2, Java 17+, Maven 3.6.3+, and Maven Failsafe Plugin 3.6.1. Examples use endpoint `GET /ping` returning the exact body `pong`, HTTP port `18081`, and JMX port `19091` to keep the two port types clearly separated.

## 2. Four Integration Phases and Two Plugins

Maven's `default` lifecycle follows a key sequence:

~~~text
validate
   |
compile
   |
test-compile
   |
test                         -> Surefire: unit tests
   |
package                      -> JAR/WAR, Boot repackage if configured
   |
pre-integration-test         -> Spring Boot Maven Plugin: start
   |
integration-test             -> Maven Failsafe Plugin: integration-test
   |
post-integration-test        -> Spring Boot Maven Plugin: stop
   |
verify                       -> Maven Failsafe Plugin: verify
~~~

Role table:

| Phase | Bound goal | Inputs | Outputs / PASS condition |
| --- | --- | --- | --- |
| `test` | `surefire:test` | `*Test.java`, test classes, test runtime | Unit tests finish, reports in `target/surefire-reports` |
| `package` | `jar:jar`, optionally `spring-boot:repackage` | Compiled classes, resources, dependencies | Packaged artifact; not an integration test |
| `pre-integration-test` | **`spring-boot:start`** | Application classpath, main class, runtime config, ports | Forked app process starts and JMX admin is ready |
| `integration-test` | **`failsafe:integration-test`** | `*IT.java`, running endpoint, test config | Failsafe runs ITs, writes results; does not fail build immediately on *test assertion failure* |
| `post-integration-test` | **`spring-boot:stop`** | JMX port/name matching the process started by start | Requests closing Spring ApplicationContext so process can exit |
| `verify` | **`failsafe:verify`** | IT results in `target/failsafe-reports` | Passes/fails build based on integration test results |

**Key insight:** integration test assertion outcomes **must not halt the build immediately in the `integration-test` phase**. If you run tests with Surefire or a goal that fails immediately during that phase, Maven skips `post-integration-test` and leaves the application running. Failsafe uses one goal to run tests and another goal to decide the final outcome after cleanup.

**Scope caveat:** a process crash, plugin error, dependency resolution failure, killed Maven process, CI runner disconnect, or an exception in `stop` can still prevent the lifecycle from reaching `stop`, even though Failsafe defers *test failures*. Do not treat this as an unconditional cleanup guarantee across every possible failure mode.

## 3. Why Use `spring-boot:start` Instead of `spring-boot:run`?

| Property | `spring-boot:run` | `spring-boot:start` |
| --- | --- | --- |
| Typical purpose | Run the application during development | Keep the app running for subsequent goals, especially integration tests |
| Can Maven proceed to goals after start? | `run` blocks Maven until the app stops | **Yes**, `start` returns once its startup check passes |
| Process | Configurable fork/run depending on plugin settings | Launches a **separate process** for the IT app |
| Automatic lifecycle shutdown | No natural counterpart paired with run | Has companion goal **`spring-boot:stop`** |
| Stop mechanism | Manual stop/other logic | JMX manages the started application |
| Suitable for `mvn verify` HTTP ITs | Inconvenient when run blocks | **Yes**, when bound to pre/post-integration-test |

`spring-boot:start` normally **does not run `java -jar target/...jar`** against the packaged executable JAR; it launches the app from compiled classes and the classpath assembled by the plugin. Therefore, ITs using `start/stop` verify HTTP runtime behavior, **but do not automatically prove the final repackaged JAR runs standalone via `java -jar`**. If your release requires verifying the actual archive, add a separate smoke test for the packaged artifact.

## 4. Two Easily Confused Ports: HTTP and JMX

The **HTTP port** serves HTTP requests exposed by the Spring Boot application (e.g., `18081`); integration tests call `http://127.0.0.1:18081/ping`.

The **JMX port** serves process management started by the Spring Boot Maven Plugin (e.g., `19091`; the plugin default is `9001`). `spring-boot:stop` locates the application admin MBean over this connection. The two ports **serve unrelated purposes** and both must be available.

~~~text
Maven process
   |
   | spring-boot:start (JMX control; plugin config jmxPort=19091)
   v
Forked Spring Boot process
   | HTTP listener: 18081                -> integration test GET /ping
   | JMX admin listener: 19091           -> spring-boot:stop sends shutdown command
   |
   v
Maven continues failsafe:integration-test -> post-integration-test:stop -> verify
~~~

**Rule:** when changing `jmxPort`, place it in **plugin-level `<configuration>`**, so `start` and `stop` share **the same value**; if you only override the port for `start` while `stop` still uses default `9001`, `stop` will not find the process to shut down. Likewise, if the HTTP server listens on `18081` while tests target `8080`, Failsafe fails to connect even though JMX works fine.

Parameters worth remembering:

| Boot plugin parameter | Default / example value | Meaning |
| --- | --- | --- |
| `jmxPort` | Default `9001`; example `19091` | Management port that `start` and `stop` must share |
| `jmxName` | `org.springframework.boot:type=Admin,name=SpringApplication` | Admin MBean name; must also match if changed |
| `arguments` | `--server.port=18081` | Arguments passed to the Spring app; controls HTTP port |
| `profiles` | List of Spring profiles | Specifies active profiles for the started process |
| `environmentVariables` | Runtime key/value pairs | Environment variables for the forked process |
| `systemPropertyVariables` | JVM properties for the forked process | Passes JVM settings to the app |
| `wait` | Default `500` ms | Interval between startup readiness checks |
| `maxAttempts` | Default `60` | Maximum check attempts; ~30 seconds by default |
| `skip` | `false` | Skips the goal when policy requires; must stay in sync with Failsafe |

Increasing `maxAttempts`/`wait` when an app starts slowly can help in CI environments; however, inspect startup logs and root causes because timeouts often indicate a missing DB, wrong profile, or insufficient JVM memory. **`start`'s JMX readiness** does not guarantee all business services or Actuator readiness probes are healthy; tests must still verify the contracts they depend on.

## 5. Complete Maven POM: An Application with Unit Tests and HTTP Integration Tests

This example uses **Spring Boot starter parent** to minimize boilerplate plugin configuration, keeping the focus on coordinating start/stop with Failsafe. Corporate parent / standalone BOM setups are covered separately in section 9.

File layout:

~~~text
boot-it-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/
    │       ├── BootItApplication.java
    │       └── PingText.java
    └── test/
        └── java/dev/example/
            ├── PingTextTest.java
            └── PingIT.java
~~~

### 5.1. `pom.xml` with Phase-Bound Executions

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>boot-it-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <it.http.port>18081</it.http.port>
        <it.jmx.port>19091</it.jmx.port>
    </properties>

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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <!-- Same JMX port for both start and stop -->
                    <jmxPort>${it.jmx.port}</jmxPort>
                </configuration>
                <executions>
                    <execution>
                        <id>pre-integration-test</id>
                        <phase>pre-integration-test</phase>
                        <goals>
                            <goal>start</goal>
                        </goals>
                        <configuration>
                            <arguments>
                                <argument>--server.port=${it.http.port}</argument>
                            </arguments>
                            <wait>500</wait>
                            <maxAttempts>120</maxAttempts>
                        </configuration>
                    </execution>
                    <execution>
                        <id>post-integration-test</id>
                        <phase>post-integration-test</phase>
                        <goals>
                            <goal>stop</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <classesDirectory>${project.build.outputDirectory}</classesDirectory>
                    <systemPropertyVariables>
                        <it.http.port>${it.http.port}</it.http.port>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <phase>integration-test</phase>
                        <goals>
                            <goal>integration-test</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>verify-integration-tests</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**POM explanation:**

- Starter parent `4.1.2` manages dependency versions and related Maven settings. When `spring-boot-maven-plugin` is declared, parent repackage configuration normally produces an executable JAR during `package`.
- `spring-boot-starter-webmvc` provides MVC/web server support; `spring-boot-starter-test` provides JUnit Jupiter and the test library suite.
- `maven-surefire-plugin` version `3.6.1` runs **unit tests** at the `test` phase using default patterns, which `PingTextTest` matches.
- `spring-boot-maven-plugin` binds **`start` at `pre-integration-test`** and **`stop` at `post-integration-test`**. Global `jmxPort` is shared. Only the `start` execution needs `--server.port=...`.
- `maven-failsafe-plugin` version `3.6.1` binds **`integration-test` at the `integration-test` phase** and **`verify` at the `verify` phase**. Failsafe receives the HTTP port via JVM system property `it.http.port`.
- `<classesDirectory>${project.build.outputDirectory}</classesDirectory>` directs Failsafe to load compiled application classes from `target/classes` rather than relying on the internal layout of the repackaged Boot executable JAR. Spring Boot starter parent already configures this field, though declaring it explicitly keeps the example clear and helps when switching parents.
- The two properties `it.http.port` and `it.jmx.port` prevent hardcoding values in multiple places. In CI, you can override them with `-Dit.http.port=...` and `-Dit.jmx.port=...`, as long as both ports are free and all goals/tests share the same settings.
- `wait=500` and `maxAttempts=120` allow up to roughly 60 seconds for startup (per the plugin's readiness polling mechanism), instead of the ~30-second default.

**Do not bind Failsafe's `verify` goal to the `integration-test` phase:** Failsafe must perform verification **after** `post-integration-test`, so cleanup can execute before Maven reports a build failure on assertion errors.

### 5.2. Java 17 Application

File **`src/main/java/dev/example/PingText.java`**:

~~~java
package dev.example;

public final class PingText {
    private PingText() {
    }

    public static String body() {
        return "pong";
    }
}
~~~

File **`src/main/java/dev/example/BootItApplication.java`**:

~~~java
package dev.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootItApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootItApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return PingText.body();
    }
}
~~~

`@SpringBootApplication` enables Spring Boot application mechanisms, while `@RestController` and `@GetMapping` expose the HTTP endpoint for testing. The program listens for HTTP traffic on the port passed via `--server.port=...` when `start` launches the process.

### 5.3. Unit Test `PingTextTest.java`: Runs Before the App Starts

File **`src/test/java/dev/example/PingTextTest.java`**:

~~~java
package dev.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PingTextTest {
    @Test
    void returnsPong() {
        assertEquals("pong", PingText.body());
    }
}
~~~

`PingTextTest` does not require a running application. Surefire matches the default `*Test.java` pattern, so it runs at the `test` phase, **before `package` and `pre-integration-test`**. This test checks only pure logic and does not prove the HTTP endpoint works.

### 5.4. Integration Test `PingIT.java`: Calls the App Running in Another Process

The following file **`src/test/java/dev/example/PingIT.java`** is **Java 17**-compatible and is a complete class:

~~~java
package dev.example;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PingIT {
    @Test
    void answersOverRealHttp() throws IOException, InterruptedException {
        int port = Integer.parseInt(
                System.getProperty("it.http.port", "18081"));

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/ping"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

**Compatibility note:** In Java 17, `java.net.http.HttpClient` does not yet implement `AutoCloseable`, so do not wrap `HttpClient` in `try-with-resources`. This example creates the client and sends the HTTP request directly; it compiles with JDK 17 when the project declares JUnit Jupiter and uses the `pom.xml` above. If upgrading Java, verify APIs and resource management for the target version.

The test calls a real HTTP address using the JDK HttpClient. It **does not** use `@SpringBootTest` to open a second application context inside the test JVM. When testing an app started by Maven `start`, sending real HTTP requests is the simplest and most verifiable approach.

- The class name `PingIT` matches Failsafe's default `*IT.java` pattern; Surefire does not treat it as `*Test.java` by default.
- The port comes from system property `it.http.port` configured in Failsafe in the POM, allowing port changes via a single Maven property.
- `assertEquals(200, ...)` verifies status; `assertEquals("pong", ...)` verifies the **exact** response body with no trailing newline.
- `HttpClient.send` throws `IOException` if the app is not listening on the port, or `InterruptedException` if interrupted; Failsafe records the corresponding test failure/error.
- No application startup code is needed inside the test; Maven `spring-boot:start` already started it in `pre-integration-test`.

## 6. Running the Right Command and Inspecting Results

From the example's root directory with JDK 17+ and a compatible Maven installation:

~~~bash
mvn -version
mvn clean verify
~~~

**The right command to run is `mvn clean verify`**. It executes all required phases up through `verify`. Do not use `mvn integration-test` as the primary CI command, because it **stops before `post-integration-test`** and skips both `stop` and verification.

Expected log sequence (milestones only, not verbatim stdout):

~~~text
... maven-surefire-plugin:3.6.1:test ...
... maven-jar-plugin:jar ...
... spring-boot-maven-plugin:4.1.2:repackage ...
... spring-boot-maven-plugin:4.1.2:start (pre-integration-test) ...
... maven-failsafe-plugin:3.6.1:integration-test ...
... spring-boot-maven-plugin:4.1.2:stop (post-integration-test) ...
... maven-failsafe-plugin:3.6.1:verify ...
[INFO] BUILD SUCCESS
~~~

**Logs may vary in execution IDs, plugin versions, timestamps, and other details depending on Maven; the phase order is what to verify.**

Report output:

~~~text
target/
├── classes/...
├── test-classes/...
├── boot-it-demo-1.0.0.jar
├── surefire-reports/                 # unit tests
│   └── TEST-dev.example.PingTextTest.xml
└── failsafe-reports/                 # integration tests
    ├── TEST-dev.example.PingIT.xml
    └── failsafe-summary.xml
~~~

Completion checkpoints:

- `PingTextTest` is discovered by Surefire, at least 1 unit test runs, and 0 failures/errors occur.
- `PingIT` is discovered by Failsafe, at least 1 integration test runs, and 0 failures/errors occur.
- `failsafe-summary.xml` and Failsafe `verify` report no errors.
- Spring Boot start/stop appear in the proper order.
- Once Maven finishes, no HTTP listener from the IT process remains on port `18081`, unless another application independently occupies that port.

On Windows you can use `mvnw.cmd clean verify` if the project **already has a Maven Wrapper**; the example does not generate one automatically. On Linux/macOS, `./mvnw clean verify` is the equivalent when a wrapper is present.

## 7. Proving a Test Failure Still Lets `stop` Run

To verify Failsafe's behavior in a controlled way, temporarily change the integration test assertion (on a test branch) to an incorrect expected value:

~~~java
assertEquals("not-pong", response.body());
~~~

Then run:

~~~bash
mvn clean verify
~~~

Expected logical sequence:

1. The app starts via `spring-boot:start` in `pre-integration-test`.
2. `PingIT` executes in `failsafe:integration-test`; the assertion **FAILS** and results are saved.
3. Because this is a *test failure* whose build failure Failsafe defers, Maven still advances to `post-integration-test`.
4. `spring-boot:stop` is invoked to shut down the application context.
5. `failsafe:verify` detects the earlier test failure; Maven exits with **`BUILD FAILURE`**.

In the Failsafe report, the failure message looks like:

~~~text
PingIT: expected <not-pong> but was <pong>
~~~

Exact assertion messages vary by JUnit version; this illustrates **meaning**, not verbatim stdout. After the exercise, restore `assertEquals("pong", response.body())` and re-run `mvn clean verify`.

**Why not use Surefire to run ITs at the `integration-test` phase?** Surefire can fail the build immediately upon assertion failure, preventing Maven from reaching `post-integration-test`. Failsafe is specifically designed to **defer failure until `verify`**, ensuring teardown runs during normal test assertion failures.

**Caveat to remember:** if `spring-boot:start` fails to launch the app, if the Maven JVM crashes unexpectedly, if the build is canceled, or if another goal raises a fatal error before `stop`, there is no guarantee `post-integration-test` will run. In strict CI setups, add a final runner-level cleanup step, isolate processes/containers, and verify ports after the build.

## 8. Distinguishing JMX Readiness, HTTP Readiness, and Business Readiness

`spring-boot:start` uses an admin MBean inside the forked process and polls its status to determine when the Spring application is ready according to the **plugin's startup check**. This reduces race conditions compared to launching `java -jar` in the background and immediately running tests.

However, the three readiness levels are not identical:

| Level | Evidence | What it proves |
| --- | --- | --- |
| **Startup control** | `start` completes, MBean is found | Process is managed by the Boot plugin and application startup met plugin criteria |
| **HTTP availability** | Integration test calls `GET /ping` and receives 200 and `pong` | Web listener and target route are working |
| **Business readiness** | Health/readiness probes, DB/message broker, business operations | System satisfies dependencies/contracts required by the test case |

Completion of `start` **does not guarantee** that an external database is seeded, a broker is connected, or a specific tested endpoint responds properly. Those conditions belong to integration test assertions and health checks. If complex readiness gating is needed, use Actuator properly or a bounded retry strategy in tests; never conflate the JMX control port with the HTTP port.

### `start` Timeout

Defaults are `maxAttempts=60` and `wait=500` ms, giving roughly 30 seconds of wait time. If a project needs longer startup in CI, increase the limits intentionally and document why. Timeouts should never be infinite, as that can mask DB failures, Java/port misconfigurations, or beans failing to initialize.

## 9. When a Project Does Not Use Starter Parent

If a project inherits from a **corporate parent** or only imports the `spring-boot-dependencies` BOM, you must account for all inherited mechanisms yourself. You cannot declare both a corporate parent and Boot parent directly in the same `pom.xml`.

Three independent responsibilities:

1. **Dependency management:** import `spring-boot-dependencies` into `dependencyManagement` so starters and third-party dependencies resolve compatible versions.
2. **Build plugin management and packaging:** declare explicit versions for `spring-boot-maven-plugin`, compiler, surefire, and failsafe; if an executable JAR is needed, bind `spring-boot:repackage` to the `package` phase if the parent does not provide that execution.
3. **IT lifecycle:** bind `spring-boot:start` to `pre-integration-test`, `spring-boot:stop` to `post-integration-test`, and Failsafe `integration-test` + `verify` to their phases.

**A detail specifically highlighted by Spring Boot documentation:** starter parent configures Failsafe with:

~~~xml
<classesDirectory>${project.build.outputDirectory}</classesDirectory>
~~~

When not using starter parent, declare this explicitly in Maven Failsafe Plugin. Without appropriate configuration, Failsafe may try to use the repackaged executable JAR rather than compiled classes, causing tests to fail to load application classes via standard classpath paths. The complete POM in section 5 also includes this property explicitly so learners do not overlook it when switching parents.

**Additional snippet when importing the BOM (not a standalone POM):**

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

And when Boot parent does not supply the repackage execution, declare the goal on the Boot plugin alongside start and stop executions:

~~~xml
<execution>
    <id>repackage</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
~~~

The `<execution>` snippet above belongs inside `<executions>` of **`spring-boot-maven-plugin` itself**, alongside start and stop—not Failsafe. If a corporate parent already provides a `repackage` execution, inspect the effective POM to avoid duplicate declarations that run the goal twice.

## 10. How to Skip Integration Tests Without Starting the App Unnecessarily

During quick local iterations, you may want to skip integration tests while still compiling/packaging the application. Passing only a Failsafe property like `-DskipITs` **may not** skip the Boot `start/stop` goals; Maven could still launch the server even though no ITs run.

The solution is to use **a single property controlling all three goals**:

1. Boot `start`: skipped when `skip.it=true`.
2. Boot `stop`: skipped when `skip.it=true`.
3. Failsafe `integration-test` / `verify`: skipped via the same property.

Example default property in the POM:

~~~xml
<properties>
    <skip.it>false</skip.it>
</properties>
~~~

Below are **supplementary configuration fragments** to merge into the existing plugin/execution definitions—do not create duplicate `<properties>` or `<configuration>` blocks:

~~~xml
<!-- Inside execution spring-boot:start -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>

<!-- Inside execution spring-boot:stop -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>

<!-- Inside maven-failsafe-plugin -->
<configuration>
    <skip>${skip.it}</skip>
</configuration>
~~~

**Note when applying:** the `start` execution already has `<configuration><arguments>...`, so **add `<skip>${skip.it}</skip>` inside that existing `<configuration>`**; do not create two sibling configuration blocks. Failsafe already has `classesDirectory` and `systemPropertyVariables`, which must remain inside the same configuration block.

**Do not put `<skip>${skip.it}</skip>` at the global Spring Boot plugin level** if `repackage` still needs to run, because `skip` can cause the packaging goal to be skipped too. Skip only **the start/stop executions**.

Once fully configured:

~~~bash
mvn clean verify -Dskip.it=true
~~~

skips ITs, `start`, and `stop`, while running other configured checks. This command **cannot serve as a CI quality gate claiming full IT coverage**; use it only when policy permits.

## 11. How to Verify Results After Maven Runs

### Evidence 1: effective POM

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

In the generated file, look for these executions:

- `spring-boot:start` → `pre-integration-test`.
- `failsafe:integration-test` → `integration-test`.
- `spring-boot:stop` → `post-integration-test`.
- `failsafe:verify` → `verify`.
- `jmxPort` shared by both Boot goals; HTTP port passed to both the app and tests with the same value.

### Evidence 2: test reports

~~~text
target/surefire-reports/TEST-dev.example.PingTextTest.xml
target/failsafe-reports/TEST-dev.example.PingIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Do not rely solely on `BUILD SUCCESS`. If `PingIT` is missing from the reports, the integration test **may not have run**. By default, Failsafe matches patterns like `**/IT*.java`, `**/*IT.java`, `**/*ITCase.java`; verify package, class name, test engine, and reports.

### Evidence 3: process stopped

After `mvn clean verify`, the IT application should have exited. In the example, `http://127.0.0.1:18081/ping` no longer returns `pong` from the build's forked process. Do not treat an idle port as the sole proof: cross-check `stop` logs and process/port ownership for that build, as another application might reuse the port.

**Do not run `mvn integration-test` to "save phases"**: Maven will not execute `post-integration-test` and `verify`. If you already ran it and the app is still alive, you can invoke `spring-boot:stop` in the same project with the matching `jmxPort`, though you should not assume it handles every process/JMX edge case. If `stop` fails, terminate the build's process using appropriate operational controls.

## 12. Avoiding Port and State Conflicts During Parallel CI Runs

The example uses:

~~~text
HTTP app port: 18081
JMX admin port: 19091
~~~

These are **two fixed ports** for learning clarity. When multiple modules, branches, or two CI jobs run concurrently on the same host/network namespace, ports can collide.

Solutions:

- **Isolate each job** in its own container/runner, or assign a dedicated HTTP/JMX port pair per application and per job.
- When using property overrides, change both HTTP and JMX consistently, for example:

~~~bash
mvn clean verify -Dit.http.port=18082 -Dit.jmx.port=19092
~~~

- For integration tests needing ephemeral ports, you can use **Build Helper Maven Plugin** to reserve a port in an early phase, pass it to `<arguments>--server.port=...` and simultaneously to Failsafe `<systemPropertyVariables>`; Spring Boot documents an official example. However, "reserving a port" cannot completely eliminate races if the port is released before the app binds, so CI still needs isolation or bounded retries.
- When changing the JMX port, **keep the same `jmxPort` for start and stop**; when changing the HTTP port, tests must target the exact value passed to the app.
- Never have tests on machine A call `localhost` assuming the app runs on machine B; Failsafe and the forked Boot process in this example share the same network namespace. If CI splits jobs/containers, pass hosts/ports according to actual topology.

**Risk with multiple instances:** colliding JMX/HTTP ports can cause `start` to fail binding or cause `stop` to target an unrelated process. Good operational practice isolates namespaces, tags processes, and logs exact connection targets.

## 13. Slow Startup, Readiness, and External Dependencies

When an app depends on a database, broker, or external service, `start` may time out or application startup may fail. Troubleshoot in order:

1. Read the forked Spring Boot process log for the root exception, not only the "Failed to connect to JMX" line.
2. Check the active Spring profile, `environmentVariables`, JVM arguments, and application configuration.
3. Verify both the HTTP port and JMX port are free.
4. Ensure test dependencies are provisioned in CI before `pre-integration-test` (Testcontainers, Docker Compose, or CI service containers per design).
5. Adjust `wait` and `maxAttempts` within reasonable bounds when extra startup time is genuinely needed, without masking root causes.
6. In ITs, assert endpoints and business contracts rather than relying solely on `start` returning.
7. Add end-of-job cleanup so leftover test data or processes do not linger after abnormal failures.

If your integration tests already start the application via `@SpringBootTest(webEnvironment=RANDOM_PORT)` inside the test JVM, **you do not need `start/stop` simultaneously just to get an HTTP server**. The two strategies serve different goals:

| Strategy | Who starts the app? | When is it appropriate? |
| --- | --- | --- |
| `@SpringBootTest` with test server | Spring TestContext inside the test JVM | Tests using dependency injection, application context, mocks/customizers, and embedded server |
| Maven `spring-boot:start/stop` + Failsafe | Boot plugin launches a separate process | Black-box HTTP testing from outside the app process, or tools that do not create a Spring context directly |
| `java -jar` smoke test | Script/CI launches the executable archive | Verifying the actual release artifact, Boot loader, and runtime packaging |

You do not need all three in every project. Pick the strategy matching the contract you need to prove.

## 14. Multi-Module Builds and Start/Stop Ordering

Example Maven reactor:

~~~text
platform-parent/             packaging=pom
├── core/                    packaging=jar (library)
├── data/                    packaging=jar (library)
└── web-app/                 packaging=jar (Spring Boot application)
~~~

**Bind `start/stop` only to modules that require a running application**, such as `web-app`. The parent `pom` has no main application, and library modules have no HTTP server to start. You can define shared plugin versions/defaults in the parent's `pluginManagement`, then activate the executions only in the web module.

If modules build **in parallel** via Maven `-T`, watch out for:

- Concurrent apps/modules must not contend for the same HTTP/JMX ports.
- Maven reactor dependency order does not manage test databases or external process lifecycles across modules.
- If one module's IT calls another service, provision those services explicitly in CI or dedicated profiles.
- An inherited `start` execution leaking into every child module can break the reactor because library modules lack a main class.

**Review rule:** check `mvn help:effective-pom` on the specific module to confirm `start/stop` appear only on application modules.

## 15. Common Errors and Diagnostics

| Symptom | Likely cause to check | How to resolve |
| --- | --- | --- |
| `mvn integration-test` finishes, yet app keeps running | Did not reach `post-integration-test` | Use `mvn verify` / `mvn clean verify`; stop leftover process safely |
| `mvn verify` does not run `start` | Plugin execution unbound, profile inactive, or wrong module | Inspect effective POM, ID, phase, goals, reactor |
| App listens on HTTP 18081, but IT calls 8080 | Ports in Failsafe and start are out of sync | Share common property `it.http.port` |
| `spring-boot:stop` cannot find MBean | Mismatched JMX port/name, app crashed, or another process holds port | Use plugin-level `jmxPort` for start/stop; inspect startup logs |
| `Address already in use` on start | HTTP/JMX port conflicts with another job or leftover process | Assign dedicated ports, isolate runners, clean up owned processes |
| `start` timeout | App not ready, config/DB error, missing JDK, or slow startup | Inspect forked process logs; adjust wait/maxAttempts intentionally |
| `PingIT` runs too early in Surefire | Surefire pattern/config modified to include `*IT` | Keep Surefire `*Test` and Failsafe `*IT` patterns separate |
| `BUILD SUCCESS`, but no IT reports | Failsafe goals unbound, skip flag set, or tests undiscovered | Check Failsafe reports and `PingIT` naming; enforce non-zero policy |
| Integration test fails, and stop never runs | Fatal plugin/start error, killed Maven, or Failsafe verify bound to wrong phase | Ensure Failsafe verify runs **after** stop; add CI cleanup fallback |
| Failsafe fails to load app classes | Not using starter parent; wrong `classesDirectory` with repackaged JAR | Configure `${project.build.outputDirectory}` |
| `@SpringBootTest` starts another server on a different port | Mixing Boot plugin start with Spring test context server | Use black-box HTTP tests or pick one consistent strategy |
| Test passes even though the app is dead | IT only calls methods/mocks without hitting the running process over HTTP | Use real JDK HttpClient/RestClient and assert status/body |
| App refuses to exit after stop is called | Spring ApplicationContext closed, yet non-daemon threads/resources remain active | Shut down thread pools/schedulers and verify process termination |
| Parallel CI flakes | Fixed ports, shared DB, unisolated test data | Use isolated environments and dedicated ports/databases |
| `mvn package` skips integration tests | Stops before `pre-integration-test` | Use `mvn verify` to execute the IT lifecycle |

To trace failures, identify the **first failing goal/phase**, inspect its inputs, and correlate Maven logs with Surefire/Failsafe reports and forked process state. Never paper over failures by clearing random caches or skipping required tests.

## 16. QA Gate for CI

A baseline integration pipeline should enforce:

| Gate | PASS condition | Evidence |
| --- | --- | --- |
| Valid Maven/JDK | Wrapper/build tool and Java meet requirements | `mvn -version`, version files |
| Unit tests | `PingTextTest` executed with zero failures | Surefire XML |
| Packaging | Appropriate executable archive produced if releasing a JAR | Boot repackage log, `jar tf` |
| Boot start | Process starts and JMX admin responds properly | `spring-boot:start` log, startup log |
| Integration tests | `PingIT` discovered and HTTP status/body match | Failsafe XML |
| Boot stop | `spring-boot:stop` executes; process exits | Maven goal log, port/process check |
| Failsafe verify | IT results evaluated and build passes/fails accurately | `failsafe:verify` + Maven exit code |
| Abnormal cleanup | No leftover IT processes spawned by the pipeline | CI finally/post-job cleanup |

**If policy requires ITs, `Tests run: 0` is a quality FAIL even if Maven exits 0.** You can enable `failIfNoTests` in Failsafe configuration when appropriate, while checking how it interacts with teardown if it fails at execution time; maintain solid CI cleanup for early failures.

Never expose Maven/JMX debug ports to public networks. In CI environments, open ports only within trusted network namespaces, manage environment variables/credentials carefully, and keep secrets out of logs.

## 17. Self-Check Exercises

**Question 1.** Why is `spring-boot:run` inconvenient to place before Failsafe integration tests?

**Answer:** `run` normally keeps Maven blocked waiting until the app terminates; `start` is designed not to block the pipeline, letting Maven proceed to run tests and then shut down the app with `stop`.

**Question 2.** Which phase does `spring-boot:start` belong to, and which phase does `spring-boot:stop` belong to?

**Answer:** Bind `start` to `pre-integration-test` and `stop` to `post-integration-test`. Maven does not bind either goal automatically unless executions are configured.

**Question 3.** Why does Failsafe require two goals: `integration-test` and `verify`?

**Answer:** The first runs and records ITs; the second evaluates results after cleanup finishes. That way a normal assertion failure does not prevent Maven from running `post-integration-test`.

**Question 4.** Why is `mvn integration-test` insufficient?

**Answer:** It stops before `post-integration-test` and `verify`, so the app may remain running and final IT results are not evaluated.

**Question 5.** Is HTTP port `18081` the same as JMX port `19091`?

**Answer:** No. The HTTP port serves application endpoints; the JMX port is the plugin's management channel to stop the process. The two values are independent and must each be configured on their respective targets.

**Question 6.** How do `PingTextTest` and `PingIT` differ?

**Answer:** `PingTextTest` is a unit test run by Surefire during the `test` phase; `PingIT` sends HTTP requests to the Spring Boot process launched by `start` and is run by Failsafe during `integration-test`.

**Question 7.** A project uses a corporate parent and imports the Boot BOM. What must you watch out for?

**Answer:** Importing the BOM does not supply plugin executions. You must configure Boot start/stop, Failsafe integration-test/verify, and plugin versions; also set `classesDirectory=${project.build.outputDirectory}` when not using starter parent so Failsafe loads classes properly.

**Question 8.** A test assertion fails. Is the process guaranteed to always stop?

**Answer:** Under normal Failsafe flow, assertion failures are deferred so `post-integration-test` runs. However, fatal errors, killing Maven, JVM crashes, or `stop` errors can prevent cleanup; keep fallback cleanup in CI.

**Question 9.** Is enabling `-DskipITs` only for Failsafe enough to prevent the app from starting?

**Answer:** Not guaranteed. You must synchronize skipping across Boot `start/stop` and Failsafe to avoid starting the server unnecessarily.

**Question 10.** Does running `mvn clean verify` mean the executable JAR was tested via `java -jar`?

**Answer:** Not necessarily. `spring-boot:start` uses compiled classes/classpath per the plugin; running a `java -jar` archive smoke test is an additional check when artifact packaging is part of the release contract.

## 18. Ready-to-Use Checklist

- [ ] Compatible Spring Boot/JDK/Maven versions and required starters selected.
- [ ] Boot `start` bound to `pre-integration-test`, `stop` bound to `post-integration-test`.
- [ ] Maven Failsafe `integration-test` bound to `integration-test`; `verify` bound to `verify`.
- [ ] Same `jmxPort`/`jmxName` shared by start and stop, distinct from the HTTP port.
- [ ] App receives `--server.port` accurately, and ITs receive the matching port via JVM property.
- [ ] IT classes match Failsafe patterns such as `*IT.java`; unit tests match Surefire `*Test.java`.
- [ ] Use `mvn clean verify` to run the full lifecycle; avoid stopping at `integration-test`.
- [ ] Inspect Surefire/Failsafe XML, test counts, failures/errors—never just `BUILD SUCCESS`.
- [ ] Verify the app process exits after stop; keep fallback cleanup if the lifecycle aborts early.
- [ ] With a corporate parent, pin plugin versions, bind repackage if needed, and set Failsafe `classesDirectory` properly.
- [ ] When skipping ITs, synchronize skip across Boot start, Boot stop, and Failsafe.
- [ ] In parallel CI runs, isolate ports or network namespaces per app/job.
- [ ] For executable releases, add a `java -jar` check if verifying the packaged archive directly.

**Remember:** **`pre-integration-test: start → integration-test: Failsafe runs ITs → post-integration-test: stop → verify: Failsafe concludes`**. The start/stop pair manages application lifecycle while Failsafe manages test execution and failure reporting; running the full `mvn verify` lifecycle shuts down the app before Maven fails on test assertions.

## 19. Official Documentation

1. [Spring Boot Maven Plugin 4.1.x — Running Integration Tests; start/stop](https://docs.spring.io/spring-boot/maven-plugin/integration-tests.html)
2. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
4. [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/index.html)
5. [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
6. [Maven Failsafe Plugin — Test Pattern / JUnit Platform](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/junit-platform.html)
7. [Maven Failsafe Plugin — integration-test Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
8. [Maven Failsafe Plugin — verify Goal](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
