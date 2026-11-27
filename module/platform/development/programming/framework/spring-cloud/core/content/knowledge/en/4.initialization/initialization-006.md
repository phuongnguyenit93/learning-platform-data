# Running Applications with Maven, Gradle, and Executable JAR

This lesson belongs to the **Initialization** chapter of the **SPRING_CLOUD_CORE** module. The goal is to know how to build, run, package, and verify a Spring Boot application using Spring Cloud abstractions with two common tools—**Maven** and **Gradle**—and then run the application from an **executable JAR** in a near-production setup.

In a distributed system, merely starting a new process is only the first step. The application must also load the right configuration, use a compatible Spring Boot/Spring Cloud version pair, register or look up services when discovery is integrated, and expose enough signals to verify its status. The commands in this lesson use version placeholders; replace them with the compatible version set chosen by your project.

## 1. Learning Outcomes

After this lesson, you can:

1. Distinguish between running an application from source code and running an executable JAR package.
2. Use the Maven Wrapper or Gradle Wrapper to resolve dependencies, compile, test, and package the application.
3. Configure the Spring Boot Maven Plugin or Gradle Boot Plugin to produce an artifact runnable with `java -jar`.
4. Pass profiles, ports, and external configuration when starting the application.
5. Inspect the dependency tree and avoid pairing an incompatible Spring Cloud version with Spring Boot.
6. Run multiple local instances to observe discovery and service communication.
7. Diagnose common issues such as the wrong JDK, missing dependencies, ports already in use, missing configuration, or registry connection failures.

## 2. Build and Run Model

Basic workflow:

~~~mermaid
flowchart TD
    SRC["Source code + configuration"] --> BUILD["Maven or Gradle"]
    BUILD --> DEPS["Resolve dependencies"]
    DEPS --> COMPILE["Compile and test"]
    COMPILE --> PACKAGE["Package executable JAR"]
    PACKAGE --> ART["Artifact .jar"]
    ART --> JVM["java -jar"]
    SRC --> DEV["spring-boot:run / bootRun"]
    DEV --> JVMDEV["JVM runs from development classpath"]
    JVM --> CONFIG["Profile + environment + command line"]
    JVMDEV --> CONFIG
    CONFIG --> APP["Spring ApplicationContext"]
    APP --> CLOUD["Spring Cloud abstractions / integrations"]
~~~

There are two common ways to run:

- **Running directly via plugin:** `spring-boot:run` with Maven or `bootRun` with Gradle. This is convenient during development because the plugin runs the application from the project's compiled classes and runtime classpath.
- **Running an executable JAR:** build the artifact first, then launch it with `java -jar`. This verifies the packaged artifact and closely matches how a standalone Spring Boot application is deployed.

Both approaches use the same source code, but classpath environments and argument passing can differ. Therefore, test both the plugin run command and the packaged artifact before releasing.

## 3. Prerequisites and Environment Setup

### 3.1. Required Tools

- A JDK supported by the chosen Spring Boot version.
- Maven or Gradle; prefer the Wrapper committed with the project.
- An IDE/editor and terminal.
- Access to repositories hosting dependencies.
- If the application uses discovery or Config Server: registry/config server endpoints and any credentials required for the test environment.
- An HTTP tool such as `curl` to verify endpoints.

Verify JDK and Wrappers:

~~~bash
java -version
./mvnw -version
./gradlew --version
~~~

On Windows PowerShell or Command Prompt, use `mvnw.cmd` and `gradlew.bat`. You do not need Maven/Gradle installed globally if the project provides a Wrapper. The Wrapper selects the build tool version declared in the project; a compatible JDK must still be installed.

### 3.2. Why Use a Wrapper?

Wrappers ensure every team member and CI pipeline runs the same Maven/Gradle version, reducing machine-specific differences. A Wrapper does **not** select the right JDK on its own, nor does it guarantee dependency repositories are reachable.

If a Wrapper fails to run:

1. Check that the JDK is in `PATH` and `JAVA_HOME` points to a valid JDK.
2. Check script execute permissions on Unix-like OSes.
3. Check proxy settings, DNS, and access to Maven/Gradle distribution URLs.
4. Do not arbitrarily swap Wrapper versions when hitting a network error or missing JDK.

### 3.3. Checking Project Structure

A single-module project typically has a structure similar to:

~~~text
spring-cloud-lab/
├── mvnw
├── mvnw.cmd
├── gradlew
├── gradlew.bat
├── pom.xml                  # if using Maven
├── build.gradle.kts         # if using Gradle Kotlin DSL
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   │       ├── application.yml
│   │       └── application-local.yml
│   └── test/
│       └── java/
└── README.md
~~~

Usually a project chooses Maven **or** Gradle as its primary build system. The layout above illustrates the Wrapper files that may appear in a repository; there is no need to maintain both build systems if the project uses a single tool.

## 4. Choosing Spring Boot and Spring Cloud Versions Before Building

Spring Cloud is released as a **release train**. Each release train supports only specific Spring Boot lines. Dependencies downloading without errors does not prove the chosen versions are compatible.

Before running build commands, determine:

- The JDK supported by the project.
- The Spring Boot version.
- The Spring Cloud release train compatible with that Boot version.
- Build plugin versions and additional dependencies.
- Which starters/integrations are actually needed, such as a discovery provider or load balancing.

Use the **Spring Cloud BOM** to manage Cloud module versions within the same release train. Do not assign independent versions to individual Cloud libraries without a verified, specific reason.

### 4.1. Maven Configuration Example

Core sections of `pom.xml`:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_COMPATIBLE_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-cloud-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>REPLACE_WITH_SUPPORTED_JDK_VERSION</java.version>
        <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <!-- Add only when the application needs client-side load balancing -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
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

The `REPLACE_WITH_...` strings are placeholders that must be replaced with actual versions. You cannot build the sample until they are replaced. This example uses the Spring Boot parent to manage Boot dependencies; if a project already uses an internal parent or another BOM, integrate the Spring Cloud BOM into the existing structure rather than adding a second parent.

The LoadBalancer starter is only an example for an application that needs client-side service ID resolution and instance selection. It does not provide a registry server or automatically register the application into Eureka/Consul. A registry provider requires its own dependency and configuration.

### 4.2. Gradle Kotlin DSL Configuration Example

In `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_COMPATIBLE_BOOT_VERSION"
    id("io.spring.dependency-management") version "REPLACE_WITH_PLUGIN_VERSION"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Add only if the application needs client-side load balancing
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

In the snippet above, Java toolchain 17 is purely illustrative. Change it to a JDK supported by your project's Spring Boot version and available in your build environment. The Spring Boot plugin version, dependency management plugin version, and Spring Cloud release train must all be selected deliberately.

You can move the release train version into `gradle.properties` for centralized management; if so, replace the variable declaration in the build script with the corresponding property lookup. Do not mix dependency management approaches from multiple plugins without understanding their resolution order.

### 4.3. When Do You Need a Cloud Starter?

Key guidelines:

- A Spring Boot starter provides the dependency bundle and auto-configuration for its corresponding Boot capability.
- Spring Cloud Commons contains shared abstractions; many integration starters pull Commons in as a transitive dependency.
- Spring Cloud LoadBalancer provides client-side instance selection when properly integrated.
- Eureka, Consul, or other providers require their corresponding integration modules and registry connection settings.
- Spring Cloud Context provides application context mechanisms and refresh scope; having the dependency does not mean every bean refreshes automatically.
- The BOM manages versions; it **does not automatically add** every Cloud library to the application.

Add only the starters you need. Unused dependencies increase startup time, expand the configuration surface, and raise conflict risks.

## 5. Building and Running with Maven

### 5.1. Running Directly During Development

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

Run with a specific profile and port:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=local --server.port=8081"
~~~

The plugin launches the application from the development classpath. After modifying source code, rebuild/restart or use a suitable reload mechanism. This path is convenient for testing configuration quickly, but does not replace testing the final packaged artifact.

### 5.2. Compiling and Running Tests

~~~bash
./mvnw test
~~~

This runs tests in the `test` phase. If the project configures integration tests in a separate phase, run the matching profile or Maven plugin goal. Do not assume `test` covers multi-service, registry, or external infrastructure tests.

### 5.3. Packaging the Application

~~~bash
./mvnw clean package
~~~

On success, Maven typically places the artifact in `target/`. The filename depends on `artifactId`, `version`, and final name configuration. Check the actual file rather than guessing the JAR name.

Run the artifact:

~~~bash
java -jar target/spring-cloud-lab-1.0.0.jar
~~~

If you need to specify a profile and port:

~~~bash
java -jar target/spring-cloud-lab-1.0.0.jar --spring.profiles.active=local --server.port=8081
~~~

If the project does not produce an executable JAR, verify that `spring-boot-maven-plugin` is declared and executes the `repackage` goal during the `package` lifecycle.

### 5.4. Inspecting Dependencies with Maven

~~~bash
./mvnw dependency:tree
~~~

Filter results to the Spring Cloud group when needed:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
~~~

When conflicts occur, read the dependency tree to pinpoint which library pulls in an unexpected version. Do not patch errors by adding random versions to child dependencies; check the BOM, parent, and dependency management first.

## 6. Building and Running with Gradle

### 6.1. Running Directly

~~~bash
./gradlew bootRun
~~~

Run with application arguments:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local --server.port=8081'
~~~

Quoting syntax depends on the shell. On Windows Command Prompt, double quotes can be used around the argument value. In multi-project/multi-module builds, run the task on the target module or use its full task path.

### 6.2. Running Tests and Packaging

~~~bash
./gradlew test
./gradlew clean bootJar
~~~

The Gradle Boot Plugin produces an executable archive via the `bootJar` task. Artifacts are typically written under `build/libs/`. If a project builds both a plain Java JAR and a Boot JAR, make sure to distinguish the two artifacts.

Run the package:

~~~bash
java -jar build/libs/spring-cloud-lab-1.0.0.jar
~~~

Pass profile and port:

~~~bash
java -jar build/libs/spring-cloud-lab-1.0.0.jar --spring.profiles.active=local --server.port=8081
~~~

### 6.3. Inspecting Dependencies with Gradle

Inspect runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect why a specific dependency version was resolved:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
~~~

Configuration names may vary depending on plugins and modules. In multi-module projects, run the task against the module containing the application.

## 7. What Is an Executable JAR and Why Verify It?

A standard Java JAR is an archive of classes and resources. A **Spring Boot executable JAR** is packaged in a layout that the Boot launcher can execute directly, typically containing:

- Application classes and resources.
- Runtime dependencies bundled alongside the application.
- Metadata identifying the launcher and the application's main class.

As a result, an executable JAR can normally be launched with:

~~~bash
java -jar app.jar
~~~

A file ending in `.jar` is not guaranteed to be a runnable Spring Boot executable JAR. If running it reports no main manifest attribute or a missing class, inspect the artifact type and plugin configuration.

You can list the archive contents using the JDK:

~~~bash
jar tf target/spring-cloud-lab-1.0.0.jar
~~~

In the standard Boot JAR layout, you will see directories such as `BOOT-INF/classes` and `BOOT-INF/lib`. Exact layout details may vary by version/configuration; the goal is to verify that application classes and runtime dependencies are packaged inside.

### 7.1. Comparing Run Commands

| Run method | Artifacts/inputs used | Primary purpose |
| --- | --- | --- |
| `spring-boot:run` | Output classes and dependencies from the Maven project. | Development, fast configuration testing. |
| `bootRun` | Runtime classpath of the Gradle project. | Development, fast configuration testing. |
| `java -jar app.jar` | Packaged artifact. | Verifying the deployable package and standalone execution. |

If running via a plugin succeeds while the JAR fails, missing resources, profiles, runtime dependencies, or packaging plugin settings may be the cause. Always test the exact artifact that will be released.

## 8. Passing Configuration at Runtime

Spring Boot supports externalized configuration. The same artifact can accept different values per environment without rebuilding, as long as the application is designed to read those properties.

### 8.1. Basic Configuration

Example `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  greeting: "Hello from local default"
~~~

Local profile in `application-local.yml`:

~~~yaml
server:
  port: 8081

app:
  greeting: "Hello from local profile"
~~~

Activate the profile:

~~~bash
java -jar app.jar --spring.profiles.active=local
~~~

Or via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=local java -jar app.jar
~~~

Environment variable syntax in PowerShell differs from Bash:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar app.jar
~~~

### 8.2. Configuration Precedence

Multiple sources can supply the same property: config files, profiles, environment variables, command-line arguments, or integrated config sources. Spring Boot defines precedence rules across property sources; consult documentation for your exact version when determining which source wins.

A helpful verification step is changing a value in a lab environment across different sources, restarting, and observing the effective value. Avoid configuring the same key across multiple sources in production without clear conventions.

### 8.3. Loading Additional External Config Files

You can specify an extra configuration directory at runtime:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./config/
~~~

The `./config/` directory must exist if providing files there; the `optional:` prefix allows the application to proceed when the location is absent. `spring.config.additional-location` adds search locations; `spring.config.location` has replacement semantics over default locations, so use it only when you intend to take full control over all config locations.

Never place passwords, tokens, or private keys directly in a repository or committed config file. Use a secret store or the deployment platform's secret injection mechanism, restrict read permissions, and avoid printing secret values to logs.

### 8.4. JVM Arguments and Application Arguments

These two argument groups sit on opposite sides of `-jar`:

~~~bash
java -Xms256m -Xmx512m -Duser.timezone=UTC -jar app.jar --spring.profiles.active=local --server.port=8081
~~~

- Before `-jar`: JVM options such as heap sizing and system properties (`-D...`).
- After the JAR filename: application arguments, typically Spring Boot command-line properties like `--server.port=8081`.

Placing arguments in the wrong position can cause the JVM to fail or the application to miss expected configuration.

## 9. Running Multiple Instances to Experiment with Spring Cloud

A Spring Boot application can run as multiple processes from the same artifact with different ports and instance metadata. For example, open two terminals:

Terminal A:

~~~bash
java -jar app.jar --spring.profiles.active=local --server.port=8081
~~~

Terminal B:

~~~bash
java -jar app.jar --spring.profiles.active=local --server.port=8082
~~~

Both processes share the same `spring.application.name` if they are two instances of the same service. When a discovery provider is present, configure each instance to register a host/port reachable by other services. When running inside containers or across multiple hosts, `localhost` in one environment does not refer to the same host in another.

### 9.1. What to Verify

- Both processes are actually running and listening on two different ports.
- Application name / Service ID matches when they belong to the same logical service.
- The registry records each instance with the correct host and port.
- The caller's discovery client sees the expected list of instances.
- The load balancer selects a valid instance and requests actually reach the target process.
- When stopping one process, registry updates, caching, and instance selection behave according to the configured mechanism.

**Launching two processes alone does not create service discovery.** You need the corresponding dependency/provider, configuration, and registry. Spring Cloud Commons defines abstractions; it does not start a Eureka/Consul server automatically.

### 9.2. Application Configuration and Refresh Scope

If the application uses `@RefreshScope`, running via Maven, Gradle, or JAR does not change how refresh scope works. Beans only reflect new values when the configuration source is actually updated and a supported refresh process is triggered. Editing an environment variable in a terminal after a process is already running does not alter that running process's environment.

When testing refresh across multiple instances, track the configuration revision on each instance. One instance refreshing does not imply the remaining instances automatically refresh. Operational workflows need a mechanism to distribute updates and verify consistent state per system requirements.

## 10. Verifying the Application After Startup

An application is considered started when logs show the context completed and the server is listening; however, you still need to verify functionality and dependencies.

### 10.1. Checking HTTP Endpoints

If the application defines controller endpoints:

~~~bash
curl -i http://localhost:8081/
~~~

Adjust the path to match your application's actual API. An HTTP 404 may indicate the endpoint path does not exist, not necessarily that the process isn't running. Connection refused typically indicates no process is listening on that host/port or the connection is blocked.

### 10.2. Checking Actuator If Installed and Configured

If the Actuator dependency is on the runtime classpath and endpoints are exposed appropriately:

~~~bash
curl -i http://localhost:8081/actuator/health
~~~

Health, readiness, metrics, and other management endpoints depend on dependencies, configuration, security, and Spring Boot version. Do not assume they exist automatically or are publicly exposed. In production, expose only needed endpoints and secure them with appropriate network policies and authentication.

### 10.3. Checking Spring Cloud Status

For applications with discovery or config integrations, verify additionally:

- The Service ID the application registers.
- Registry host/port and connection status.
- Instance ID, host, port, and metadata.
- Lookup results from the caller's side.
- Active configuration values and profiles used by the application.
- Startup logs showing which integrations were auto-configured.

Do not conclude discovery is working just because logs mention a library name. Perform an actual lookup or request through the abstraction/client.

## 11. A Repeatable Development and Release Workflow

A concise workflow for each change:

1. Verify the JDK and build tool versions via the Wrapper.
2. Check dependency changes, especially Spring Boot parent/BOM and Spring Cloud BOM.
3. Run compile/tests; resolve dependency errors before editing code.
4. Run the plugin (`spring-boot:run` or `bootRun`) with the local profile for quick validation.
5. Package the executable JAR.
6. Run that exact JAR locally with configuration externalized from the artifact.
7. Verify endpoints, health/readiness if present, discovery, and an end-to-end service call if applicable.
8. Record JDK, Boot, Cloud, build tool versions, and run commands in deployment logs or release metadata.

Minimal CI example with Maven:

~~~bash
./mvnw --batch-mode clean verify
~~~

With Gradle:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

Actual CI tasks depend on project configuration; ensure integration tests and packaging run properly. Do not add `-DskipTests` or `-x test` as a default workaround when a build fails.

### 11.1. Reproducibility

To allow others to reproduce a build, store or control:

- The Wrapper and repository configuration.
- The JDK/toolchain version.
- Plugin versions and dependency management.
- BOM and release train versions.
- Required build profiles (if any).
- Artifact name, checksum, and source commit/version.

Do not use dynamic dependency versions or uncontrolled snapshots in production releases without an appropriate pinning and verification process.

## 12. Common Errors and How to Handle Them

| Symptom | Possible cause | Troubleshooting direction |
| --- | --- | --- |
| `Unsupported class file major version` or bytecode error | JDK used to run/build does not match bytecode/plugins. | Check `java -version`, `JAVA_HOME`, toolchain, and IDE/CI JDK. |
| Cannot resolve dependency | Repository, proxy, DNS, credentials, or wrong coordinates/version. | Check repository access and Maven/Gradle logs; avoid blindly bumping versions. |
| Spring Boot/Spring Cloud compatibility error | Release train does not support the Boot line in use or dependency overridden. | Check compatibility matrix, BOM, and dependency tree. |
| Maven run works but JAR fails to run | Repackage plugin not configured, wrong artifact executed, or missing runtime dependency. | Inspect plugin config, JAR type, and archive contents. |
| Gradle `bootRun` succeeds but `bootJar` fails | Packaging task, main class, resources, or runtime configuration differs. | Run `clean bootJar`, inspect task logs, and test the right artifact. |
| `Port already in use` | Another process occupies the port. | Stop the old process or pick another port via `--server.port`. |
| App starts but calls by service ID fail | Missing LoadBalancer/provider, misconfigured registry, or empty lookup. | Check dependencies, service ID, registry, and instance list. |
| Cannot connect to registry | Wrong host/port, DNS, firewall, credentials, or registry not ready. | Test from the application's runtime environment, not just the host machine. |
| Config file edited but output unchanged | Config source not reloaded; bean cached old value; missing refresh/restart. | Inspect Environment, property sources, scope, and refresh process. |
| Actuator returns 404 | Missing starter, endpoint not exposed, different management port/path. | Check dependencies, endpoint exposure, security, and management config. |
| Plugin run works but JAR cannot find config file | External file exists, but working directory at runtime differs. | Specify explicit location, check working directory and file permissions. |

When diagnosing, change one variable at a time. Changing JDK, Boot, Cloud BOM, profile, and registry simultaneously makes it very hard to identify what fixed the issue.

## 13. Hands-On Exercise: Packaging and Running Two Instances

### Objective

Create a simple Spring Boot application with an endpoint returning the application name and instance ID. Build it using **either** Maven or Gradle, run it with the plugin, then package and run it via the executable JAR. If your environment has a discovery provider, register both instances to observe them.

### Steps

1. Create an application with a test endpoint, such as `GET /info`.
2. Set `spring.application.name=inventory-service` and configure a distinct `instance-id` via environment variable or property.
3. Confirm the JDK and Boot/Cloud version pair.
4. Run tests and start the app using the build plugin.
5. Package the JAR and list the archive contents.
6. Run two processes from the same artifact on ports 8081 and 8082, each with a different instance ID.
7. Call each port's endpoint and verify the response matches each instance.
8. If registry integration is present, confirm both instances appear in the registry and a caller can look up the service ID.
9. Stop one instance and observe registry/cache/caller behavior; note convergence time and any transient errors.
10. Restart it and verify recovery.

Simple endpoint example:

~~~java
@RestController
class InstanceController {
    private final Environment environment;

    InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/info")
    Map<String, String> info() {
        return Map.of(
            "application", environment.getProperty("spring.application.name", "unknown"),
            "instance", environment.getProperty("app.instance-id", "local")
        );
    }
}
~~~

This is an illustrative snippet for the test endpoint; import Spring Web, Spring Environment, and `Map` per your project structure. In production, do not expose internal details beyond what operational policy allows.

Run two processes from the same artifact:

~~~bash
java -jar app.jar --server.port=8081 --app.instance-id=inventory-a
java -jar app.jar --server.port=8082 --app.instance-id=inventory-b
~~~

Open two separate terminals to run them concurrently. Do not run both commands sequentially in the same terminal if the first process has not exited.

### Results Table

| Check | Expected result | Actual result |
| --- | --- | --- |
| Build/test | Tasks finish without errors. | Record your own |
| Plugin run | Endpoint responds as expected. | Record your own |
| Executable JAR | Runs via `java -jar`. | Record your own |
| Instance A/B | Distinct ports and IDs. | Record your own |
| Registry (if any) | Both instances advertised with accurate addresses. | Record your own |
| Stop A | Behavior observed when one instance goes down. | Record your own |
| Restore A | Instance returns per provider mechanism. | Record your own |

## 14. Completion Checklist

- [ ] Can verify the JDK and build tool via the Wrapper.
- [ ] Can explain how Maven `spring-boot:run` differs from `package` + `java -jar`.
- [ ] Can explain how Gradle `bootRun` differs from `bootJar` + `java -jar`.
- [ ] Can configure the Spring Boot Maven Plugin or Gradle Boot Plugin to build an executable JAR.
- [ ] Can select a compatible Spring Cloud release train and manage versions with the BOM.
- [ ] Can pass profiles, ports, JVM options, and application arguments in the correct positions.
- [ ] Can load configuration from external files or environment variables per environment.
- [ ] Can distinguish running multiple processes from configuring discovery/registry.
- [ ] Can verify the actual packaged artifact rather than only running from an IDE/plugin.
- [ ] Know how to inspect health, dependencies, registry, and startup logs when the app fails.
- [ ] Can record versions and run commands to reproduce the environment.

**References to consult during practice:** Spring Boot Reference on build systems, Maven/Gradle plugins, executable archives, and externalized configuration; the Spring Cloud release train/compatibility matrix and documentation for the integration in use. Always check against your project's exact version before copying configuration into production.
