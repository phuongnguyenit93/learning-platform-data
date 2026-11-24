# Running `run`, `start`, `stop`, and `help` Goals for the Right Purpose in Spring Boot Maven Plugin

## 1. Choose the Right Goal Before Typing a Command

When developing a Spring Boot application with Maven, you may need to **run the app for quick local testing**, **start the app for lifecycle integration tests**, **stop the exact app started by the plugin**, or **look up plugin configuration options**. These four needs correspond to four distinct goals of `spring-boot-maven-plugin`:

| Goal | Purpose | Does the Maven Invocation Wait While the App Runs? | When Should You Use It? |
| --- | --- | --- | --- |
| `spring-boot:run` | Runs the application directly from project classes/resources and dependency classpath. | **Yes**: foreground invocation, typically holding the terminal while the app runs. | Local development, testing endpoints, debugging, or checking config while editing code. |
| `spring-boot:start` | Starts the application in a separate process, verifies startup status, and **returns control** to Maven. | **Does not wait until app shutdown**; only waits for startup/readiness within configured limits. | Before running integration tests that require a live application. |
| `spring-boot:stop` | Requests shutdown of the application previously managed by `start`. | Ends as soon as the stop request completes. | After integration tests, in `post-integration-test`, or manually stopping a `start` session. |
| `spring-boot:help` | Prints goal and configuration parameter details of the plugin. | Does not run the application. | Checking property names, data types, defaults, and parameters supported by the current plugin version. |

**One-sentence rule:** *`run` for development*, *`start` + `stop` for lifecycle management during testing*, *`help` for reference*. All four are **Maven plugin goals**; they are **not** HTTP endpoints, not equivalent to `java -jar`, and do not replace `mvn test` / `mvn verify` on their own.

The full plugin coordinates are `org.springframework.boot:spring-boot-maven-plugin`. The shorthand `spring-boot:...` prefix works when Maven resolves the plugin from the POM/plugin metadata. Best practice is using the project's Maven Wrapper and declaring the plugin in `pom.xml` so everyone runs the intended version.

> **Version context:** the hands-on exercise uses Spring Boot **3.3.13**, Java 17, and compatible Maven; this is an illustrative baseline to explain behavior, not a claim of being the latest release. Consult the plugin docs **for your project's exact version** in case goal/property names or operational behavior differ.

## 2. Goals and the Maven Lifecycle: Do Not Confuse How They Are Invoked

A Maven *phase* (such as `compile`, `test`, `package`, `integration-test`, `verify`) can trigger multiple configured plugin goals. A *goal* is a specific action executed by a plugin.

Two common invocation styles:

~~~bash
# Directly invoke a goal of Spring Boot Maven Plugin
./mvnw spring-boot:run

# Execute Maven phases, during which bound goals may run
./mvnw verify
~~~

When invoking `spring-boot:run` directly, the developer intentionally launches the app for local use. When binding `start`, `failsafe:integration-test`, `stop`, and `failsafe:verify` to the Maven lifecycle, `mvn verify` can **automatically coordinate** starting the app, running tests, stopping the app, and reporting results. Many learners mistakenly assume adding the Spring Boot plugin alone enables integration tests in `verify`; in reality, **Failsafe/tests and proper executions must be configured**.

### 2.1. Relation to `package` and `repackage`

- `spring-boot:run`: runs from the build classpath; **not** a test of whether the packaged executable JAR works.
- `spring-boot:start`: also launches the app for build/test automation; not a "production JAR launch" in the deployment sense.
- `spring-boot:stop`: closes the lifecycle opened by `start`; does not manage all JVMs on the host.
- `spring-boot:help`: displays plugin documentation only.
- `spring-boot:repackage`: a **separate** goal that builds an executable archive from an existing JAR/WAR. To verify the actual deliverable artifact, run `mvn clean package` followed by `java -jar target/<actual-file-name>.jar` (for the matching artifact).

For a Web app with endpoints, a successful `run` **is not enough** to replace unit tests, integration tests, artifact packaging, smoke tests, or release quality gates.

## 3. `spring-boot:run` — Local Execution, Foreground Invocation

### 3.1. Prerequisites

The project needs a Spring Boot application class with `public static void main(String[] args)`, classpath dependencies, and the Spring Boot Maven Plugin. In a Maven project with Java sources, Maven prepares required outputs based on configuration and goal; when separating build errors from runtime errors, running `./mvnw test-compile` first clearly isolates compilation status.

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell/cmd, when using the project's Maven Wrapper
mvnw.cmd spring-boot:run
~~~

The Maven invocation **remains attached in the terminal** while the application runs. The application actually executes inside a **forked JVM** spawned by the plugin; therefore, JVM options and system properties for the app must be passed through the right plugin channels. Do not assume Maven's `-Dfoo=bar` automatically becomes a Java system property inside the application process.

To stop `run` when running interactively, typically press **Ctrl+C in the terminal running the goal** and confirm the process has exited. `spring-boot:stop` is designed for apps managed by `start`; **do not use it as the default stop button for `run`**.

### 3.2. Passing Application Arguments Properly

Spring Boot command-line application arguments are arguments read by `SpringApplication`, such as `--server.port=18085` or `--spring.profiles.active=dev`. Plugin 3.3 provides the `spring-boot.run.arguments` property to pass them.

~~~bash
# Run the web app on HTTP port 18085
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"

# Pass two application arguments
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.application.name=goal-demo"
~~~

Once the app starts and exposes `/ping`, in another terminal run:

~~~bash
curl -i http://localhost:18085/ping
~~~

Evaluate the response by **actual** HTTP status and body, not from the words `BUILD SUCCESS` or an assumed fixed startup log. If the server defaults to 8080 or uses another port, use the exact port passed. For apps without an embedded HTTP server (such as batch/CLI apps), replace the endpoint check with job verification, exit code, or expected application output.

### 3.3. Profiles, JVM Arguments, and System Properties

| Setting Type | Command Example | Where Is It Sent? |
| --- | --- | --- |
| Spring profile | `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev,local` | Plugin shortcut to select active Spring profiles for the app. |
| Application arguments | `./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"` | Arguments passed to `main(String[] args)` for Spring Boot. |
| JVM arguments | `./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Dexample.mode=local"` | Forked JVM running the app: heap, JDWP, system properties. |
| Maven user property | `./mvnw spring-boot:run -Dsome.maven.option=value` | Maven/plugin configuration; **does not automatically become a JVM property** inside the app. |

You can also declare `<arguments>`, `<jvmArguments>`, `<profiles>`, `<systemPropertyVariables>`, or `<environmentVariables>` inside the plugin `<configuration>`. When passing multiple profiles, comma-separated format in `spring-boot.run.profiles=dev,local` is supported by the plugin.

Example default POM configuration (configuration snippet, **not a complete POM**):

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <profiles>
            <profile>local</profile>
        </profiles>
        <jvmArguments>-Xmx512m</jvmArguments>
        <arguments>
            <argument>--server.port=18085</argument>
        </arguments>
    </configuration>
</plugin>
~~~

**Distinguishing the two ports:** `server.port` is the application's HTTP port, **not** the plugin's `jmxPort` used by `start`/`stop` (see Section 4).

### 3.4. Debugging and DevTools

To attach a debugger to the application JVM, configure JDWP via `spring-boot.run.jvmArguments`. Example on a developer machine with JDWP bound only to loopback:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
~~~

With `suspend=y`, the app pauses waiting for the debugger before entering `main`; not seeing the HTTP port open yet is intentional. Never expose debug ports publicly in untrusted environments.

`spring-boot-devtools` assists development (automatic restarts/LiveReload under supported conditions); `spring-boot:run` alone does not guarantee hot reload for every Java or resource edit. Enabling `addResources=true` puts source resources directly on the classpath, which bypasses build-time filtering for those resources; check real needs before enabling it.

## 4. `spring-boot:start` — Starting for Integration Tests, Then Returning Control

`start` also spawns a separate JVM for the Spring Boot application, but serves a different purpose than `run`:

1. Starts the application and sets up status management over **JMX**.
2. Polls within `maxAttempts` and `wait` limits to detect application readiness via the plugin mechanism.
3. **Returns control to Maven** once the start step completes, while the application stays running.
4. Allows subsequent Maven goals (such as Failsafe integration tests) to interact with the live app.
5. Uses `stop` to request shutdown after tests finish.

~~~text
Maven lifecycle:
  pre-integration-test
     -> spring-boot:start     (spawn app + JMX readiness)
  integration-test
     -> failsafe:integration-test (test live HTTP/DB/services)
  post-integration-test
     -> spring-boot:stop      (lifecycle cleanup)
  verify
     -> failsafe:verify      (evaluate test results)
~~~

This chain fits build/test pipelines. `start` is **not** a daemon/service manager for running production workloads; real deployments should use the executable artifact and an appropriate process manager or container orchestrator.

### 4.1. JMX Handshake Differs from HTTP

By default, the plugin uses JMX port **9001** to communicate with the app launched by `start`. The HTTP port (Spring Boot Web defaults to 8080) is independent. If either port is occupied, change the right port and keep configuration synchronized.

| Port | Used By Whom? | Used For What? |
| --- | --- | --- |
| `server.port=18085` | Spring Boot's embedded web server. | Clients/tests call `http://localhost:18085/...`. |
| `jmxPort=19009` | Spring Boot Maven Plugin and app JVM for start/stop management. | Maven waits for startup, communicates via MBean, issues stop command. |

**Do not** send HTTP requests to the JMX port and do not point `curl` at `localhost:19009`; `curl` must target the HTTP port. The plugin uses the default MBean name `org.springframework.boot:type=Admin,name=SpringApplication`; if you customize `jmxName` or `jmxPort`, **both `start` and `stop` must share the same configuration**.

Common parameters:

- `jmxPort`: JMX port used for communication; e.g., 19009.
- `jmxName`: management MBean name; keep default unless specifically needed.
- `wait`: milliseconds between readiness checks; defaults to 500 ms in 3.3 documentation.
- `maxAttempts`: maximum readiness check attempts; defaults to 60, totaling roughly 30 seconds under defaults.
- `arguments` / `profiles` / `jvmArguments`: pass application/JVM settings similarly to `run`.
- `skip`: allows skipping the goal under approved conditions.

JMX reporting that the app has started is the signal to begin testing; **it does not replace assertions** that endpoints/DB/downstreams work properly. On startup timeout, read JVM logs and check ports, profiles, external dependencies, and JMX config before blindly increasing `maxAttempts`.

## 5. `spring-boot:stop` — Stopping the Exact App Managed by `start`

After `start` finishes, the application keeps running independently. `stop` looks up the corresponding MBean on the configured JMX port and asks the app to shut down:

~~~bash
# When the same POM configures jmxPort/jmxName for both start and stop
./mvnw spring-boot:stop
~~~

Important conditions:

- `stop` is designed for an **application started via `spring-boot:start`**.
- If `start` used JMX port 19009, `stop` must also use **19009**.
- This JMX port is **not** `server.port` and is not a Spring MVC Actuator HTTP shutdown endpoint.
- If a test, shell, or Maven process terminates abnormally before `stop`, an orphan process may remain running. Identify the exact PID and clean up safely per environment; never kill all `java` processes indiscriminately as it can affect other apps.
- In projects running multiple apps in parallel, each managed process needs a non-conflicting JMX port. Multiple modules sharing default 9001 on one host can make integration tests flaky.

Do not treat `stop` running cleanly as a test of business logic. It simply closes the lifecycle opened by `start`.

### 5.1. Why Bind to `post-integration-test`?

If you run `start` manually and forget `stop`, the app may hold ports, temp files, or test resources. Binding the pair to two Maven phases keeps the workflow consistent and CI-friendly:

~~~text
pre-integration-test : spring-boot:start
integration-test     : maven-failsafe-plugin:integration-test
post-integration-test: spring-boot:stop
verify               : maven-failsafe-plugin:verify
~~~

Failsafe is designed to **evaluate test results in `verify`**, so assertion failures in `integration-test` normally do not abort Maven before `post-integration-test` runs. However, severe build/tool errors, killed runners, or failures inside `start` itself can still interrupt cleanup; CI should have controlled process/container cleanup if the environment requires it.

## 6. `spring-boot:help` — Checking Exact Goals, Parameters, and Version

`help` does not start the application, does not use HTTP/JMX ports, and does not create an executable JAR. It is the best starting point whenever you are unsure which options a plugin version supports or which goal owns a parameter.

~~~bash
# Display overview help for Spring Boot Maven Plugin
./mvnw spring-boot:help

# Inspect all parameters specifically for the run goal
./mvnw spring-boot:help -Ddetail=true -Dgoal=run

# Inspect start and stop parameters separately
./mvnw spring-boot:help -Ddetail=true -Dgoal=start
./mvnw spring-boot:help -Ddetail=true -Dgoal=stop

# Inspect parameters of the help goal itself
./mvnw spring-boot:help -Ddetail=true -Dgoal=help
~~~

Meaning:

- `-Ddetail=true` tells `help` to display properties and fuller descriptions.
- `-Dgoal=start` selects documentation for the `start` goal; this is a **parameter to plugin help**, and does not launch the application.
- Verify the **Spring Boot Maven Plugin version** printed in output; blog posts online may document a different version than your project's.
- Do not confuse `spring-boot:help` with `help:effective-pom`: the latter belongs to the **Maven Help Plugin** and displays the resolved POM after inheritance and management.

If Maven reports `No plugin found for prefix 'spring-boot'`, verify plugin declaration and resolution via POM/repositories. You can invoke the full coordinates of a specific version:

~~~bash
./mvnw org.springframework.boot:spring-boot-maven-plugin:3.3.13:help -Ddetail=true -Dgoal=run
~~~

Calling full coordinates is useful to target a specific plugin/version without relying on prefix resolution, as long as Maven can access the plugin artifact.

## 7. Complete Example: Web App and Integration Test Lifecycle with Maven Failsafe

This example demonstrates **all four goals** while separating live-app integration tests from manual checks. It requires a working Maven Wrapper, JDK 17, reachable dependencies, and free ports **HTTP 18085 / JMX 19009**. If your project already enforces its own toolchain or port conventions, use those project values.

Structure:

~~~text
boot-goals-demo/
  pom.xml
  mvnw                      (pre-generated/committed Maven Wrapper)
  mvnw.cmd
  .mvn/wrapper/...
  src/main/java/com/example/goals/BootGoalsApplication.java
  src/test/java/com/example/goals/BootGoalsApplicationIT.java
~~~

### 7.1. Standalone POM

`pom.xml`:

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
    <artifactId>boot-goals-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>boot-goals-demo</name>

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
                <configuration>
                    <!-- Plugin JMX port; DIFFERENT from HTTP port -->
                    <jmxPort>19009</jmxPort>
                    <arguments>
                        <argument>--server.port=18085</argument>
                    </arguments>
                </configuration>
                <executions>
                    <execution>
                        <id>pre-integration-test</id>
                        <goals>
                            <goal>start</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>post-integration-test</id>
                        <goals>
                            <goal>stop</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Configuration notes:**

- `spring-boot-starter-parent` manages versions of dependencies/plugins in this example and configures packaging for executable Spring Boot JARs. If a project uses a **custom parent and imports the BOM**, you must declare plugin versions, compiler/Failsafe settings, and `repackage` appropriately—do not assume BOM import brings build defaults.
- Global `<jmxPort>19009</jmxPort>` ensures both `start` and `stop` use the same JMX port. Changing only one execution causes a mismatch.
- `<arguments><argument>--server.port=18085</argument></arguments>` sets the **HTTP** port passed to the app when `run` or `start` executes.
- Execution `pre-integration-test` binds `start` to the goal's default matching phase; `post-integration-test` binds `stop` to its matching phase. You may declare `<phase>` explicitly if your team's build conventions require it.
- Failsafe `integration-test` runs integration test classes, and `verify` checks results after cleanup. Files named `*IT.java` are picked up by Maven Failsafe's default naming convention.
- The Boot parent configures Failsafe's `classesDirectory` appropriately for Spring Boot packaging. When importing the BOM without inheriting the parent, check/configure `classesDirectory` as `${project.build.outputDirectory}` per Spring Boot documentation so Failsafe does not mistakenly read the repackaged archive.

**What to avoid:** never bind `spring-boot:run` to `pre-integration-test`, because `run` blocks the invocation in the foreground and the lifecycle cannot proceed normally to Failsafe. The `start` + `stop` pair is specifically built for this lifecycle.

### 7.2. Main Class: Easy-to-Verify Endpoint

File `src/main/java/com/example/goals/BootGoalsApplication.java`:

~~~java
package com.example.goals;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootGoalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootGoalsApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`@SpringBootApplication` enables app configuration, `@RestController` lets methods return HTTP content, and `@GetMapping("/ping")` maps GET. This Java class is **complete within a Maven project declaring Spring Boot dependencies**; it will not compile standalone with `javac BootGoalsApplication.java` without Spring Boot JARs on the classpath.

### 7.3. Integration Test Calling the Live Application

File `src/test/java/com/example/goals/BootGoalsApplicationIT.java`:

~~~java
package com.example.goals;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BootGoalsApplicationIT {
    @Test
    void liveHttpEndpointReturnsPong() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:18085/ping"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

The test uses Java 17's `HttpClient` to send a real request to the application launched by `start`. It verifies live behavior on HTTP port **18085**, without relying on `MockMvc` or booting a second Spring context inside the test JVM. Failsafe picks up `*IT` tests and JUnit Platform runs them via `starter-test`/compatible plugin versions.

**Limitation of this example:** a hardcoded port can collide across parallel builds. In parallel CI jobs, allocate a distinct port pair per job or reserve ports and pass matching ports to both the app and tests; never pick uncoordinated random ports independently.

### 7.4. Four Core Operations and Expected Results

**Try `help` first, without running the app:**

~~~bash
./mvnw spring-boot:help -Ddetail=true -Dgoal=start
./mvnw spring-boot:help -Ddetail=true -Dgoal=stop
~~~

Expected: documentation for `jmxPort` (and goal-specific parameters) appears, with no new HTTP server started.

**Try `run` in the foreground:**

~~~bash
./mvnw spring-boot:run
~~~

Expected: Web app opens HTTP port **18085** per POM config; Maven invocation holds the terminal. In another terminal:

~~~bash
curl -i http://localhost:18085/ping
~~~

Expected: HTTP **200**, response body **`pong`**. Then press Ctrl+C to stop `run` and verify port 18085 is released.

**Try `start` and `stop` manually:**

~~~bash
# If the project has not been compiled yet, prepare outputs:
./mvnw test-compile

# Goal returns control after startup; application keeps running
./mvnw spring-boot:start
~~~

Once `start` succeeds, in another terminal call:

~~~bash
curl -i http://localhost:18085/ping
~~~

After verifying, run in the project terminal:

~~~bash
./mvnw spring-boot:stop
~~~

Expected: the plugin-managed app process shuts down; new requests to HTTP 18085 no longer succeed against that instance. Do not assume `curl` prints the exact same error message across OSes when the app stops, as TCP/HTTP error phrasing varies.

**Try the entire lifecycle in one command:**

~~~bash
./mvnw clean verify
~~~

Expected phase order: compile, regular tests (if any), package, `start`, Failsafe `integration-test`, `stop`, Failsafe `verify`. Conclude success only when Failsafe reports tests actually executed with 0 failures/errors, the app stopped cleanly, and Maven exited with code 0. If this file is the only integration test, the Failsafe report must show `liveHttpEndpointReturnsPong` ran.

Typical report paths:

~~~text
target/failsafe-reports/           # integration test results
target/surefire-reports/           # unit tests via Surefire, if any
target/boot-goals-demo-0.0.1-SNAPSHOT.jar  # example executable artifact
~~~

Note: this example project has only one `*IT.java`; it does not create any `*Test.java` unit test. `mvn test` alone does not run `*IT` tests, whereas `mvn verify` with Failsafe execution does. You can add unit tests, but never mistake an empty Surefire report for proof that integration tests ran.

### 7.5. Trying an Intentional Failure Case

In the integration test, change `assertEquals("pong", response.body())` to `assertEquals("pang", response.body())` and run `./mvnw verify`. Expect the test to **FAIL** and Failsafe to record the report; Maven still proceeds to `post-integration-test` and `stop` before `failsafe:verify` fails the build. This is the exact behavior learners should observe: unlike the blocking `run` goal, the `start`/`stop` pair manages cleanup in the integration-test lifecycle.

Restore the original assertion and re-run `./mvnw clean verify`. If an app ever stays running due to an abnormal interruption, verify the exact PID/port before cleaning up so you do not terminate another JVM by mistake.

## 8. Running with a Corporate Parent or Without Starter Parent

This lesson focuses on **how to use the goals**, so the complete sample above uses the Boot starter parent for brevity. For projects keeping an internal parent and importing the `spring-boot-dependencies` BOM:

- The BOM manages **dependency versions**, and does not automatically supply the Boot starter parent's `pluginManagement`/executions.
- Declare `spring-boot-maven-plugin` with a version matching your Boot line, configure `start`/`stop` executions, and configure `repackage` on application modules needing an executable JAR.
- Declare `maven-failsafe-plugin` with a JUnit Platform-compatible version, `integration-test`/`verify` executions, and appropriate `classesDirectory`.
- Check compiler release/`-parameters`, Java version, test classpath, and JMX/HTTP settings when migrating projects.
- Only application modules with a main class and suitable web/job runtime should participate in `start`/`stop`. Parent aggregators and library modules must not boot servers just because they have the BOM.
- Run `./mvnw help:effective-pom` to inspect applied config, then use `spring-boot:help -Ddetail=true -Dgoal=start` to check parameters supported by that plugin version.

These goals do not replace Maven Failsafe's testing logic; real test execution and assertions are required to declare a pipeline passing.

## 9. Common Errors and Resolutions

| Symptom | Likely Cause | Verification Action |
| --- | --- | --- |
| `spring-boot:run` holds the terminal and looks hung. | Web server runs in foreground; this is `run`'s design. | Call endpoints from another terminal, then press Ctrl+C in the `run` terminal. |
| `-Dserver.port=18085` does not change app port during `run`. | Maven options are not forwarded automatically into the forked JVM. | Use `-Dspring-boot.run.arguments="--server.port=18085"` or plugin config. |
| `spring-boot:start` fails to return control due to startup timeout. | App not ready, JVM error, JMX port conflict, or external dependency unavailable. | Read startup logs, HTTP/JMX ports, profiles, env; then inspect `wait`/`maxAttempts` if needed. |
| HTTP app is running yet `stop` cannot find it. | App was launched via `run`/`java -jar`, or JMX port/name differs. | Check how it was started; ensure `start` and `stop` share the same `jmxPort`/`jmxName`. |
| `curl localhost:19009/ping` fails. | 19009 in the example is JMX, not HTTP. | Send requests to `http://localhost:18085/ping`. |
| `mvn test` skips `BootGoalsApplicationIT`. | Failsafe integration tests bind to phases after `test`, following `*IT` convention. | Run `mvn verify` and inspect `target/failsafe-reports`. |
| `mvn verify` succeeds yet Failsafe ran no tests. | Naming filter or missing plugin executions; report may be empty. | Check `integration-test` + `verify` executions and reported test count. |
| `mvn verify` reports port already in use. | Prior app instance still running or parallel builds sharing HTTP/JMX ports. | Find the process holding **that exact port**, stop that instance, and isolate ports. |
| `spring-boot:help` says plugin prefix not found. | POM/plugin repositories/prefix resolution misconfigured. | Inspect POM, invoke full coordinates with plugin version, check Maven settings. |
| `stop` runs before integration tests. | Execution bound to wrong phase or missing Failsafe binding. | Check `help:effective-pom` and phase logs; `start` in `pre-integration-test`, `stop` in `post-integration-test`. |
| Test fails and app remains running. | Build aborted abnormally, start/stop failed, or runner killed. | Read logs and reports, identify exact PID/JMX port, clean up per CI policy. |
| `run` passes yet executable JAR fails. | `run` uses build classes/classpath; `repackage` missing or wrong artifact. | Run `package`, inspect archive/manifest, test actual `java -jar`. |

**Diagnostic method:** first identify **which exact goal is being called and which phase is running**. Next check whether the JVM process exists, whether HTTP/JMX ports match, what startup logs say, how many tests Failsafe actually ran, and whether Maven exited 0. Never "fix" failures by skipping integration tests or disabling `stop`.

## 10. Self-Assessment Checklist

After this lesson, verify each statement below using commands and logs:

- [ ] `run` launches the app and keeps the Maven invocation waiting, even though the app executes in a forked JVM.
- [ ] `start` launches the app, waits for plugin readiness, then returns control to Maven so tests can continue.
- [ ] `stop` only manages an app started by `start`; `run` is typically stopped via Ctrl+C in the terminal.
- [ ] `help` does not start the app, and accepts `-Ddetail=true` and `-Dgoal=...` to inspect parameters.
- [ ] Distinguishes `server.port` (HTTP) from `jmxPort` (Maven plugin/JMX); configures both ports properly for their respective purposes.
- [ ] Distinguishes application arguments, JVM arguments, and Maven user properties when the app runs in a forked JVM.
- [ ] Wires `start`/`stop` to `pre-integration-test`/`post-integration-test` alongside Failsafe `integration-test`/`verify`.
- [ ] Confirms Failsafe reports show actual test execution; does not mistake `mvn test` for integration tests here.
- [ ] Runs `mvn verify` and traces test, startup, JMX, or cleanup failures to their true source.
- [ ] Does not treat `spring-boot:run` as equivalent to testing the packaged executable JAR.
- [ ] In multi-module reactors, invokes `start`/`stop` only on appropriate application modules, avoiding library modules.
- [ ] For parallel CI builds, isolates ports and cleans up processes safely without killing unrelated JVMs.

**Closing exercise:** fill out a four-row table for `run`, `start`, `stop`, and `help` covering (1) exact command invoked, (2) terminal/process/JMX/HTTP behavior observed, (3) pass/fail evidence, and (4) when to use or avoid it. Submit the Failsafe report for `BootGoalsApplicationIT`, `start` and `stop` logs, `spring-boot:help -Ddetail=true -Dgoal=start` output, `GET /ping` result, and an explanation of why an app can succeed under `run` while `package` can still fail.

## Official References

- [Spring Boot 3.3 Maven Plugin — Running your Application with Maven](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html)
- [Spring Boot 3.3 Maven Plugin — Running Integration Tests](https://docs.spring.io/spring-boot/3.3/maven-plugin/integration-tests.html)
- [Spring Boot 3.3 Maven Plugin — Help Information](https://docs.spring.io/spring-boot/3.3/maven-plugin/help.html)
- [Spring Boot 3.3 Maven Plugin — Goals](https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)

The commands in this lesson guide hands-on practice with an illustrative project. **Actual outcomes** must be verified via commands and reports in your own environment; understanding each goal is what lets you pick consistent ways to run apps across development, testing, and packaging.