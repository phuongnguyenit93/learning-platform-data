# `nativeRun`, Application Arguments, and Execution Environment in Gradle

When developing a **Spring Boot Native Image** application, two moments must be distinguished: **compiling** the application into an executable via **Spring AOT and GraalVM Native Image**, and then **running** that executable with a realistic environment configuration. In projects using the **GraalVM Native Build Tools Gradle plugin**, the `nativeRun` task handles executing this run step directly from Gradle.

This lesson focuses on using `nativeRun`, passing arguments to the Spring Boot application, setting environment variables, observing configuration outcomes, and handling differences between native mode and `bootRun` on the JVM. This is an essential step to test a native application before containerizing or deploying it to an operational environment.

## 1. What Does `nativeRun` Do?

The `org.graalvm.buildtools.native` Gradle plugin provides these primary tasks:

| Task | Responsibility | Result |
|---|---|---|
| `nativeCompile` | Compiles the application into a native executable | Produces the executable file in the build output directory |
| **`nativeRun`** | Runs the native application executable | Starts and runs the application as a native process |
| `nativeTestCompile` | Compiles the native test suite per plugin configuration | Creates the test executable |
| `nativeTest` | Runs the corresponding tests in native mode | Test results from the native image |

In typical configurations, `nativeRun` depends on the output of `nativeCompile`: if no executable exists yet or the output is out-of-date under Gradle's task model, the required build steps execute before running. Once the executable is ready, the task launches the **native build** without invoking `java -jar` and without running on the HotSpot JVM.

~~~mermaid
flowchart TD
    A["Command: ./gradlew nativeRun"] --> B["Gradle resolves tasks and dependencies"]
    B --> C["Spring AOT + Native Image build when needed"]
    C --> D["Native executable"]
    D --> E["nativeRun launches executable"]
    F["runtimeArgs"] --> E
    G["Process environment"] --> E
    E --> H["Spring Boot reads runtime configuration"]
    H --> I["ApplicationContext and business logic"]
~~~

The diagram depicts **the processing flow**; it does not mean Native Image must rebuild from scratch on every `nativeRun` invocation. Up-to-date checks, caching, and source/build configuration changes determine what work Gradle needs to re-run.

## 2. Prerequisites

The examples in this lesson assume your project already has:

- Spring Boot with the Gradle wrapper (`gradlew` on Unix or `gradlew.bat` on Windows).
- The GraalVM Native Build Tools Gradle plugin, configured compatibly with your Spring Boot/Gradle versions.
- A JDK/GraalVM with `native-image` matching your target version and platform, located by the plugin via toolchains or environment.
- An accurately determined application entry point (`mainClass`).
- Required dynamic components backed by Spring AOT and appropriate runtime hints.

From the project root directory:

~~~bash
# List native tasks available in the project
./gradlew tasks --all

# Compile the native executable
./gradlew nativeCompile

# Compile if needed and run the native executable
./gradlew nativeRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat nativeCompile
.\gradlew.bat nativeRun
~~~

If `nativeRun` is missing, first verify that the plugin was applied to the right Gradle module. In multi-module projects, you may need to qualify the task path, e.g., `:server:nativeRun` when the `server` module is where the native plugin is configured.

**Key point:** `nativeRun` is meant for local runs or testing environments. For deployment, you typically ship the built executable, package/distribution, or an appropriate container image rather than requiring Gradle on production hosts.

## 3. How Does `nativeRun` Differ from `bootRun` and `run`?

The Spring Boot Gradle plugin provides `bootRun` to run the application on the JVM. Gradle's Application plugin provides the `run` task. GraalVM Native Build Tools provides `nativeRun` to run the native executable.

| Characteristic | `bootRun` | `run` (Application plugin) | `nativeRun` |
|---|---|---|---|
| Execution mode | JVM with Spring Boot | JVM, per Application plugin config | Compiled native executable |
| Requires native compilation | No | No | Yes |
| Typical purpose | Rapid Spring Boot dev, JVM debugging | Running standard Java apps | Testing native behavior, config, and startup |
| Application arguments | `BootRun`/`JavaExec` config, often `--args` | `JavaExec` config, often `--args` | **`runtimeArgs` of GraalVM Native Build Tools** |
| JVM options | Applies to the JVM running the app | Applies to the JVM running the app | No HotSpot JVM running the app that way |

Do not assume that this syntax:

~~~bash
# Familiar --args syntax from bootRun/run
./gradlew bootRun --args="--server.port=9091"
~~~

can be copied verbatim to `nativeRun`. `NativeRunTask` is not a `JavaExec`; the plugin documentation defines **`runtimeArgs`** as the mechanism for configuring binary arguments. For one-off arguments, you can pass values via a Gradle property mapped into `runtimeArgs`, or run the executable directly (both shown below).

## 4. Distinguishing Three Layers of Arguments

When invoking Gradle, identify **which process each argument belongs to**.

| Category | Examples | Receiver | Purpose |
|---|---|---|---|
| **Gradle CLI/task** | `--info`, `--stacktrace`, `-PdemoPort=9091` | Gradle | Logging, project properties, build control |
| **Native Image build arguments** | `--no-fallback` or corresponding compiler flags | `native-image` during compilation | Shapes the generated executable |
| **Application runtime arguments** | `--server.port=9091`, `--demo.message=hello` | Spring Boot inside the native executable | Tunes application behavior at runtime |
| **Runtime environment variables** | `SERVER_PORT=9091`, `DEMO_MESSAGE=hello` | Native process and Spring Environment | Environment-specific configuration |
| **Native runtime flags** | Runtime flags supported by the GraalVM version | Native executable | Tunes certain native image runtime characteristics |

Common confusions:

- `./gradlew nativeRun --info` enables **Gradle logging**; it does not enable Spring Boot's `--debug` mode.
- `-PdemoPort=9091` sets a **Gradle project property**; it only affects the application if the build script uses that value to configure runtime arguments.
- `-Dspring.profiles.active=dev` passed on the Gradle command line can target the JVM running Gradle; do not treat it as a way to pass system properties to the native executable.
- `org.gradle.jvmargs` and `GRADLE_OPTS` apply to the Gradle/build JVM, not as a HotSpot heap setting for the native application.
- `buildArgs` and `runtimeArgs` are two separate configuration groups. `--server.port` belongs in **runtimeArgs**.

## 5. Configuring `runtimeArgs` in `build.gradle` (Groovy DSL)

Suppose the application uses Spring Boot properties `server.port` and `demo.message`. In a project with Native Build Tools applied, add to `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            // Each element is a single argument to the executable.
            runtimeArgs.add("--server.port=9091")
            runtimeArgs.add("--demo.message=hello-from-native")
        }
    }
}
~~~

Then run:

~~~bash
./gradlew nativeRun
~~~

Gradle runs the native executable with application arguments equivalent to:

~~~text
<native-executable> --server.port=9091 --demo.message=hello-from-native
~~~

These two values are parsed by Spring Boot as **command-line properties** if the application uses Spring Boot's default argument handling. For instance, `--server.port=9091` changes the HTTP port when the application is a web server and no custom code suppresses argument parsing.

You can use `runtimeArgs.addAll` to configure multiple arguments:

~~~groovy
graalvmNative {
    binaries {
        main {
            runtimeArgs.addAll(
                "--server.port=9091",
                "--demo.message=hello-from-native"
            )
        }
    }
}
~~~

Each element in the list is **a separate argument**. Do not put two space-separated arguments into one string expecting the plugin to split them like a shell.

## 6. Configuring in `build.gradle.kts` (Kotlin DSL)

If the project uses Kotlin DSL, the equivalent configuration is:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.add("--server.port=9091")
            runtimeArgs.add("--demo.message=hello-from-native")
        }
    }
}
~~~

When multiple arguments are needed:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.addAll(
                "--server.port=9091",
                "--demo.message=hello-from-native"
            )
        }
    }
}
~~~

In both DSLs, `main` represents the plugin's main application binary configuration. Configuring `runtimeArgs` affects how the plugin launches the image; **it does not hard-code `server.port=9091` permanently inside the executable**. When running the executable in another environment, supply the corresponding arguments or environment variables there.

## 7. Passing Flexible Values with Gradle Project Properties

You should not edit `build.gradle` every time you want to change a test port. You can **map** a project property to a runtime argument.

In `build.gradle` (Groovy DSL):

~~~groovy
graalvmNative {
    binaries {
        main {
            // The value reaches the executable only because we map it explicitly.
            runtimeArgs.add(
                providers.gradleProperty("demoPort")
                    .map { port -> "--server.port=" + port }
                    .orElse("--server.port=8080")
            )
        }
    }
}
~~~

Run sequentially:

~~~bash
# Uses the default 8080 from the sample configuration
./gradlew nativeRun

# Uses 9092
./gradlew nativeRun -PdemoPort=9092
~~~

In `build.gradle.kts` (Kotlin DSL), the idea is identical:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            runtimeArgs.add(
                providers.gradleProperty("demoPort")
                    .map { port -> "--server.port=" + port }
                    .orElse("--server.port=8080")
            )
        }
    }
}
~~~

`-PdemoPort` works only because **the build script reads that property and adds an argument to `runtimeArgs`**. Without that mapping, Gradle properties do not automatically appear in application arguments.

**Security note:** only use `-P` examples for non-sensitive values such as ports or test mode names. Never put passwords, access tokens, or credentials into command lines/project properties that get logged and stored in shell history; prefer runtime/CI secret mechanisms and appropriate secret stores.

## 8. Running the Executable Directly for One-Off Arguments

Once built, the easiest way to test different arguments is **running the native file directly**. Under standard Gradle plugin configurations, the main executable sits under `build/native/nativeCompile/`.

~~~bash
./gradlew nativeCompile

# Replace my-app with the actual image name inside build/native/nativeCompile/
./build/native/nativeCompile/my-app --server.port=9093 --demo.message=direct
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat nativeCompile

# Replace my-app.exe with the generated executable name.
.\build\native\nativeCompile\my-app.exe --server.port=9093 --demo.message=direct
~~~

The filename depends on `imageName`, plugin configuration, and OS. Windows typically produces a `.exe` file. With custom output configurations, inspect the `nativeCompile` task output rather than hard-coding the path above.

**Advantage:** iterate on arguments without reconfiguring Gradle, making it easy to observe runtime behavior close to how the executable will be deployed.

**Limitation:** running directly bypasses any environment preparation declared specifically on Gradle's `nativeRun` task; you must supply environment variables, working directory, and required files yourself.

## 9. Environment Variables When Running `nativeRun`

Spring Boot can read configuration from **environment variables** via `Spring Environment`. Common examples:

| Environment Variable | Corresponding Spring Boot Property | Effect |
|---|---|---|
| `SERVER_PORT` | `server.port` | Changes the web server port |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` | Selects active profiles per configuration rules |
| `LOGGING_LEVEL_ROOT` | `logging.level.root` | Sets the root logging level |
| `DEMO_MESSAGE` | `demo.message` | Custom property if read by the application |

Spring Boot's relaxed binding rule when converting property names to environment variables typically replaces dots with underscores, removes dashes, and converts to uppercase. For properties with complex structures, verify binding and formatting rules.

### Linux and macOS

~~~bash
# These two variables are set only for this command.
SERVER_PORT=9094 DEMO_MESSAGE=from-env ./gradlew nativeRun
~~~

If you need to select a profile:

~~~bash
SPRING_PROFILES_ACTIVE=local ./gradlew nativeRun
~~~

This passes variables into the Gradle process. Child processes launched by Gradle usually inherit that environment unless overridden by the task or runner configuration.

### Windows PowerShell

~~~powershell
$env:SERVER_PORT = "9094"
$env:DEMO_MESSAGE = "from-env"

.\gradlew.bat nativeRun

# Clear the two test-only values from the current PowerShell session.
Remove-Item Env:SERVER_PORT
Remove-Item Env:DEMO_MESSAGE
~~~

Before removing, save any prior values if those variables already existed and are used by other tools in your shell. The `Remove-Item` commands here assume a test session without pre-existing values.

### When Running the Executable Directly

~~~bash
SERVER_PORT=9094 DEMO_MESSAGE=from-env \
  ./build/native/nativeCompile/my-app
~~~

Gradle does not need to run once the executable is built and all external runtime dependencies are ready.

## 10. Configuring Environment Specifically on the `nativeRun` Task

GraalVM Native Build Tools exposes an `environment` property on `NativeRunTask`. You can set environment variables for **the process launched by the task**, instead of relying solely on the shell.

With Groovy DSL:

~~~groovy
import org.graalvm.buildtools.gradle.tasks.NativeRunTask

tasks.named("nativeRun", NativeRunTask) {
    environment.put("DEMO_MESSAGE", "from-native-run-task")
    environment.put("SERVER_PORT", "9095")
}
~~~

With Kotlin DSL:

~~~kotlin
import org.graalvm.buildtools.gradle.tasks.NativeRunTask

tasks.named<NativeRunTask>("nativeRun") {
    environment.put("DEMO_MESSAGE", "from-native-run-task")
    environment.put("SERVER_PORT", "9095")
}
~~~

These examples set variables **for runs managed by Gradle**; they do not bake fixed defaults into the binary. They assume the Native Build Tools version in use provides the `NativeRunTask.environment` API, as in modern plugin releases. If an older plugin version uses a different API, consult the API documentation for that exact version.

Never hard-code secrets in `build.gradle` or `build.gradle.kts`. For sensitive values, use variables supplied by the deployment platform or a CI secret store and reference them only when genuinely needed.

## 11. Spring Boot Configuration Precedence

When the same Spring property appears in multiple sources, **the higher-precedence source wins**. In Spring Boot's default configuration order, command-line properties like `--server.port=...` take precedence over system environment variables and most standard config file sources.

Example:

~~~text
application.properties:
    server.port=8080

Environment:
    SERVER_PORT=9094

Runtime arguments:
    --server.port=9096

Expected application port:
    9096
~~~

If the `--server.port=9096` runtime argument is removed, the environment value `SERVER_PORT=9094` governs the port assuming no higher-precedence property source intervenes.

A CLI verification example:

~~~bash
# If nativeRun has runtimeArgs containing --server.port=9096,
# SERVER_PORT=9094 may be overridden by the CLI argument.
SERVER_PORT=9094 ./gradlew nativeRun
~~~

Keep in mind that precedence order also involves other sources such as system properties, `SPRING_APPLICATION_JSON`, and test configurations. For diagnostics, inspect actual property sources instead of assuming all sources share equal precedence.

To avoid confusion, pick **one primary way** to configure a given property in each test environment, and document it when intentionally testing precedence.

## 12. Practice: Observing Runtime Config via an Endpoint

You can create a lesson-only endpoint to verify whether the native build reads the expected properties:

~~~java
package example.nativeapp;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RuntimeProbeController {
    private final Environment environment;

    RuntimeProbeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/runtime-info")
    Map<String, String> runtimeInfo() {
        return Map.of(
            "message", environment.getProperty("demo.message", "unset"),
            "serverPort", environment.getProperty("server.port", "8080")
        );
    }
}
~~~

This snippet assumes the project includes Spring Web. After building natively, try:

~~~bash
# Case 1: configure runtimeArgs for port 9091 and message in build.gradle.
./gradlew nativeRun
~~~

In a second terminal:

~~~bash
curl http://localhost:9091/runtime-info
~~~

Illustrative output when the example values are active:

~~~json
{
  "message": "hello-from-native",
  "serverPort": "9091"
}
~~~

Next, vary how values are supplied using environment variables or running the binary directly. This endpoint helps distinguish **what the application actually read** from **what the operator thought they passed**.

This endpoint is a learning aid; do not expose arbitrary environment variables, config paths, or secrets in a production endpoint.

## 13. Build-Time vs. Runtime Boundary in Spring AOT

A Spring Boot Native Image application must know its bean structure and critical reflection/resource needs at compile time. During Spring AOT, conditions governing bean structure may be evaluated and turned into code according to the **build environment**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway devGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway prodGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

Here `PaymentGateway`, `LocalPaymentGateway`, and `RemotePaymentGateway` are assumed to exist. If profile-dependent bean structure is fixed during AOT, launching the same executable with `SPRING_PROFILES_ACTIVE=prod` will not automatically create a bean that only existed in another profile's AOT configuration.

Conversely, values like `server.port`, endpoint URLs, timeouts, and display messages **can serve as runtime configuration** when existing beans read them without altering structural decisions locked in during AOT.

~~~mermaid
flowchart TD
    A["Build-time AOT environment"] --> B["Bean structure decisions and generated code"]
    B --> C["nativeCompile: executable"]
    C --> D["nativeRun + CLI args + env"]
    D --> E["Runtime config of existing beans"]
    D -. "Does not regenerate AOT-excluded structure" .-> F["Beans only present under other build conditions"]
~~~

**Practical principle:** use runtime parameters to vary **operational data**; for properties/profiles that change **which beans are registered**, verify whether switching them is supported in the current image or requires separate builds per configuration.

## 14. System Properties, JVM Options, and Native Runtime

A native executable can support certain `-D` and `-XX` arguments as specified by GraalVM Native Image, yet not every HotSpot JVM option makes sense in native mode.

Compare:

~~~bash
# Example runtime arguments to the native executable; exact support depends on GraalVM.
./build/native/nativeCompile/my-app \
  -Ddemo.message=from-system-property \
  --server.port=9091
~~~

~~~bash
# Gradle/JVM argument; do not use to pass config to the native app.
./gradlew nativeRun -Ddemo.message=from-gradle-jvm
~~~

The first passes an argument to the **native executable**; the second sets a property on the **Gradle process**. To pass a system property to the native executable via the Gradle task, put it in `runtimeArgs` when supported by your GraalVM version:

~~~groovy
graalvmNative {
    binaries {
        main {
            runtimeArgs.add("-Ddemo.message=from-native-runtime")
        }
    }
}
~~~

Native memory management, monitoring, or diagnostic flags vary across GraalVM versions. Check the runtime documentation for your exact version before applying flags. Do not copy HotSpot `-Xmx`, `-XX`, or agent flags to native without confirming support.

In particular, `JAVA_TOOL_OPTIONS` is intended for the Java launcher/JVM and should not be relied upon as a primary mechanism to configure a native executable. With Spring Boot, **application CLI properties and environment variables** are typically clearer and easier to operate.

## 15. Working Directory and External Resources

A native program does not receive only arguments and environment variables: it also has a **working directory**, file permissions, and paths to resources.

Suppose the application opens a file with a relative path:

~~~java
Path path = Path.of("config", "rules.json");
String json = Files.readString(path);
~~~

Relative paths resolve against the **running process's** working directory. When invoking `nativeRun` through Gradle, the working directory can be influenced by the task and Gradle project; when running the executable directly from another directory, results can change.

To avoid implicit dependencies, use absolute paths or pass the path as a runtime property, for example:

~~~bash
./build/native/nativeCompile/my-app \
  --demo.rules-file=/etc/myapp/rules.json
~~~

In application code, read this setting from Spring `Environment` or `@ConfigurationProperties` and open the corresponding file. Ensure the file actually exists and the service account has read permissions.

**Distinguish filesystem files from classpath resources:**

- External files like `/etc/myapp/rules.json` are read at runtime from the filesystem and must be provisioned in the deployment environment.
- Classpath-packaged resources may need to be identified via Spring AOT/runtime hints to be included in the native image.
- A resource sitting in a JAR or `src/main/resources` in build sources **does not mean** it is accessible via any relative filesystem path after compiling to a native executable.

With Spring Boot, an example of supplying an external config file via CLI is:

~~~bash
./build/native/nativeCompile/my-app \
  --spring.config.additional-location=optional:file:/etc/myapp/
~~~

Depending on your environment, replace `/etc/myapp/` with the actual directory. The `optional:` prefix prevents the application from failing solely because that additional config location does not exist; omit `optional:` when a missing file should be treated as a deployment error.

## 16. What Happens When Running in a Container?

`nativeRun` typically runs on the build host for development or testing. When packaging the executable into a container, the **container runtime** supplies the environment, working directory, file mounts, and arguments to the process.

Suppose you already have a Docker image named `demo-native:local` whose entrypoint executes the native binary:

~~~bash
docker run --rm \
  -p 9091:9091 \
  -e SERVER_PORT=9091 \
  -e DEMO_MESSAGE=container \
  demo-native:local
~~~

Here `SERVER_PORT` and `DEMO_MESSAGE` are passed to **the process inside the container**; they do not need to be set on the machine that ran `nativeCompile`. If the image's entrypoint/CMD defines other arguments, verify whether they get overridden or appended.

Note that values used during Spring AOT at build time may differ from container environment variables after the image is created. Testing both phases prevents running a container with a profile requiring bean structures that the image does not support.

## 17. Troubleshooting Common `nativeRun` Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `Task 'nativeRun' not found` | Native plugin not properly applied or wrong Gradle module targeted | `./gradlew tasks --all`, verify module and plugin |
| GraalVM/`native-image` not found | Toolchain/JDK/plugin not configured properly | Check build messages, selected tool, and `native-image --version` |
| Long build before server starts | `nativeRun` is compiling the native executable | Check `nativeCompile` logs; do not confuse with startup time |
| `Unknown command-line option '--args'` | Used `bootRun`/`run` syntax with `nativeRun` | Switch to `runtimeArgs` or run the executable directly |
| Port unchanged despite setting `SERVER_PORT` | `runtimeArgs` or higher-precedence property source overrides it | Inspect `runtimeArgs` and Spring property sources |
| Switching profile does not create expected bean | Bean structure was locked in by AOT at build time | Check AOT environment, generated code, and bean conditions |
| Binding/serialization error only in native | Missing runtime hints/metadata or feature incompatibility | Test failing code path and stack trace, add appropriate hints |
| JSON/template file not found | Wrong working directory, file not mounted, or missing resource hint | Distinguish filesystem paths from classpath resources |
| Port already in use | Another process is listening on the same port | Choose another port or stop the conflicting process |
| Stopping `nativeRun` leaves port occupied | Child process did not terminate as expected | Inspect PID/port with OS tools and stop the right process |

When investigating failures, distinguish **build failure** (before the executable launches), **startup failure** (Spring context fails to initialize), and **runtime failure** (fails only when invoking a feature). Each category requires inspecting different logs and inputs.

### Avoid Confusing Gradle Logs with Application Logs

~~~bash
# Gradle task/build details
./gradlew nativeRun --info
~~~

~~~groovy
// Separate setting so Spring Boot prints additional runtime debug details.
graalvmNative {
    binaries {
        main {
            runtimeArgs.add("--debug")
        }
    }
}
~~~

These two have different targets. Gradle's `--debug` flag can also generate massive build logs; do not enable it by habit in CI, especially when logs could reveal sensitive configuration.

## 18. Compatibility Testing Workflow with `nativeRun`

A small yet meaningful workflow should exercise the exact same feature on JVM and native with identical inputs:

1. **JVM baseline:** run `bootRun` with equivalent config, call `/runtime-info` and a real business flow.
2. **Native build:** run `nativeCompile`, save logs, and confirm the executable was created.
3. **Native run:** use `nativeRun`, passing identical `demo.message` and `server.port` via `runtimeArgs` or env.
4. **Comparison:** check HTTP status, JSON body, data side effects, logs, and exception handling.
5. **Precedence test:** set `SERVER_PORT` differently from the runtime argument to verify the higher-precedence source wins.
6. **File/config test:** run from a different working directory or use an external config path and observe differences.
7. **Process shutdown test:** stop the application and verify the port is released and resources close cleanly.

For HTTP applications, separate **native compilation time** from **executable startup time**. `./gradlew nativeRun` can take a long time on the first run because it must compile; using total task duration as startup time distorts measurements. To measure startup, launch the already-compiled executable under identical conditions and measure from process launch until app readiness.

## 19. Comprehensive Hands-On Lab

Goal: demonstrate full control over arguments and environment for **the exact same native binary**.

### Part A — Fixed Arguments

In `build.gradle` or `build.gradle.kts`, set:

~~~text
--server.port=9091
--demo.message=from-gradle
~~~

on `graalvmNative.binaries.main.runtimeArgs`. Run `nativeRun` and call `/runtime-info`; expect the port and message from `runtimeArgs`.

### Part B — Environment

Remove `--server.port` from `runtimeArgs`, set `SERVER_PORT=9094` in your shell, and re-run `nativeRun`. Verify the endpoint listens on port 9094. Next, add `--server.port=9091` back and confirm how precedence behaves.

### Part C — Gradle Property

Map `-PdemoPort` to `runtimeArgs` as in Section 7. Run sequentially:

~~~bash
./gradlew nativeRun -PdemoPort=9081
./gradlew nativeRun -PdemoPort=9082
~~~

Stop the previous run's process before starting the next. Verify that both port values are runtime data passed into the executable through Gradle.

### Part D — Direct Execution

Run a built executable directly:

~~~bash
./build/native/nativeCompile/my-app \
  --server.port=9083 \
  --demo.message=direct
~~~

Check `/runtime-info` on port 9083 and observe what changes when the working directory or environment changes.

### Part E — AOT Boundaries

If the application has `@Profile` or `@ConditionalOnProperty` controlling **bean definitions** at build time, compare bean structure when built under two different AOT environments. Do not expect changing a runtime profile alone to restore beans excluded from the image.

Record results in the table:

| Test Case | Delivery Method | Observed Port | Observed Message | Conclusion |
|---|---|---|---|---|
| A | Fixed `runtimeArgs` | Fill actual | Fill actual | Do application arguments work? |
| B | `SERVER_PORT` | Fill actual | Fill actual | Does environment take effect? |
| C | Mapped `-PdemoPort` | Fill actual | Fill actual | Is the Gradle property forwarded? |
| D | Direct executable | Fill actual | Fill actual | Runs without Gradle? |
| E | Profile/conditional | Fill actual | Fill actual | Distinguishes AOT build vs. runtime? |

## 20. Operational Principles to Remember

- **`nativeRun` runs the native build** and is convenient for local testing, though a run may trigger native compilation if outputs are not ready.
- **`runtimeArgs` passes arguments to the application**, whereas `buildArgs` and Gradle flags serve different purposes.
- **Environment variables belong to the runtime environment** and must be verified for precedence, permissions, and deployment delivery.
- **The executable does not carry the full Gradle environment.** When running directly or containerizing, supply appropriate arguments, environment, files, and working directory.
- **Spring AOT can lock in bean-structure decisions at build time**; runtime properties only vary behavior supported by the existing image.
- **Testing on the real executable** is essential to validate reflection/resource hints and Spring Boot business compatibility after compilation.

### References for Cross-Checking Your Tool Versions

- GraalVM Native Build Tools — Gradle plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Gradle end-to-end guide: https://graalvm.github.io/native-build-tools/latest/end-to-end-gradle-guide.html
- GraalVM — Build a Native Executable from a Spring Boot Application: https://www.graalvm.org/dev/reference-manual/native-image/guides/build-spring-boot-app-into-native-executable/

When applying this lesson to a real project, cross-check DSL examples and runtime flags against **the exact versions of Spring Boot, GraalVM, and the Gradle plugin** configured in your build.
