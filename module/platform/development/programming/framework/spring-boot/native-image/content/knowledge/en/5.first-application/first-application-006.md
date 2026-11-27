# Running a Spring Boot Native Image Binary with Arguments, Environment Variables, and Required Configuration

> **Chapter:** First Application  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Goal:** Run a Spring Boot executable compiled with Spring AOT and GraalVM Native Image; configure it via command-line arguments, environment variables, and external files; inspect effective values and recognize AOT limitations when changing configuration at runtime.

## 1. How Does Running Native Differ from Running a JAR?

Spring Boot can run as a JAR on the JVM or as a **native executable** compiled ahead of time with GraalVM Native Image. Spring AOT prepares the bean model, initialization code, and required runtime hints during the build step, then Native Image produces a binary for a specific target OS and CPU architecture.

```mermaid
flowchart LR
    A["Spring Boot code + dependencies"] --> B["Spring AOT"]
    B --> C["GraalVM Native Image"]
    C --> D["Native executable"]
    D --> E["CLI / environment / config file"]
    E --> F["SpringApplication starts"]
    F --> G["Endpoint ready"]
```

Example:

```bash
# Run JVM build
java -jar target/native-demo.jar --server.port=9090

# Run Linux/macOS native build
./target/native-demo --server.port=9090
```

The second command **does not start the HotSpot JVM**. However, if the program retains `SpringApplication.run(..., args)` and standard Spring Boot configuration, it still understands properties such as `server.port`, `logging.level.root`, and `spring.config.additional-location`.

Distinguish **application arguments** from **JVM launcher flags**. Forms like `--server.port=9090` are Spring Boot arguments. Flags such as `-Xms`, `-Xmx`, and `-XX:...` used with `java` are not automatically valid flags for a native executable. Memory tuning for a native binary must rely on options supported by GraalVM Native Image and the specific binary.

Native binaries are typically built separately for Linux, Windows, or macOS and a specific CPU architecture such as `x86_64` or `aarch64`. A Linux binary will not run natively on Windows, and the binary also depends on system libraries if dynamically linked.

## 2. Sample Application to Observe Configuration

Assume a Spring Boot project with `spring-boot-starter-web`. Create an endpoint that reads a configuration value from Spring's `Environment`. This example needs no database to keep testing simple.

**`src/main/java/com/example/nativedemo/NativeDemoApplication.java`**

```java
package com.example.nativedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class NativeDemoApplication {

    private final Environment environment;

    public NativeDemoApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(NativeDemoApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting() {
        return environment.getProperty(
                "app.greeting",
                "Hello from Spring Boot Native Image");
    }
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  application:
    name: native-demo

server:
  port: 8080

app:
  greeting: "Hello from default configuration"

logging:
  level:
    root: INFO
```

In this example, `app.greeting` is an application **custom property**. `/greeting` lets you immediately see which property value was selected from a file, environment variable, or startup argument.

### Build the Executable

The project requires a JDK/GraalVM compatible with Spring Boot and the **GraalVM Native Build Tools** plugin configured. With build infrastructure in place:

```bash
# Maven: use the project's native profile
./mvnw -Pnative native:compile

# Or Gradle: use the task provided by the native plugin
./gradlew nativeCompile
```

Common output locations:

| Build tool | Common path | Notes |
|---|---|---|
| Maven | `target/<executable-name>` | Name depends on `artifactId`, `finalName`, or plugin |
| Gradle | `build/native/nativeCompile/<executable-name>` | Name depends on build configuration |
| Windows native | `<executable-name>.exe` | Must be built for Windows |
| Linux/macOS native | `<executable-name>` | Needs execute permission and matching OS |

**Subsequent commands assume the Linux/macOS executable is `target/native-demo`.** Replace it with the exact path produced by your actual project. This lesson focuses on operating the built binary; Maven/Gradle commands may require extra plugin configuration depending on the project.

## 3. Method 1 — Passing Command-Line Arguments

The familiar Spring Boot syntax is `--spring.property=value`. With the sample application:

```bash
./target/native-demo \
  --server.port=9090 \
  --app.greeting="Hello from command line"
```

Once the application is ready, open a second terminal:

```bash
curl --fail --show-error http://127.0.0.1:9090/greeting
```

Expected output:

```text
Hello from command line
```

On Windows PowerShell (using a binary **built for Windows**):

```powershell
.\target\native-demo.exe --server.port=9090 --app.greeting="Hello from PowerShell"
```

Table of useful arguments:

| Argument | Effect |
|---|---|
| `--server.port=9090` | Sets the application HTTP port |
| `--server.address=127.0.0.1` | Binds only to loopback, suitable for local testing |
| `--logging.level.root=WARN` | Reduces overall log level |
| `--app.greeting="..."` | Overrides a custom application property |
| `--spring.profiles.active=prod` | Selects configuration profile; must account for AOT bean topology limits |
| `--spring.config.additional-location=optional:file:./config/` | Adds an external configuration directory |
| `--spring.config.location=file:/etc/native-demo/application.yml` | Replaces default config search locations with the specified location |

**Be careful when using the CLI:**

- Write `--server.port=9090` accurately; do not substitute `-Dserver.port=9090` out of `java -jar` habit.
- Use shell-appropriate quoting when values contain spaces, `$`, or `&`.
- By default, Spring Boot adds command-line arguments to `Environment`. If the app explicitly calls `SpringApplication.setAddCommandLineProperties(false)`, these properties will not be loaded by default.
- Do not pass passwords/tokens via the command line when safer mechanisms exist: they can show up in process listings, shell history, or log aggregators.

## 4. Method 2 — Providing Environment Variables

Environment variables are suited to running **the same binary** across local, CI/CD, Docker, or Kubernetes. Spring Boot applies relaxed binding to many property names: dots and hyphens in property names map to uppercase with underscores.

| Spring property | Common environment variable | Meaning |
|---|---|---|
| `server.port` | `SERVER_PORT` | Web server port |
| `app.greeting` | `APP_GREETING` | Demo message |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` | Profile |
| `logging.level.root` | `LOGGING_LEVEL_ROOT` | Log level |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` | JDBC URL if using a database |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` | Database username |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` | Database password |

**Bash (Linux/macOS):**

```bash
export SERVER_PORT=9091
export APP_GREETING="Hello from environment variable"
export LOGGING_LEVEL_ROOT=INFO

./target/native-demo
```

In another terminal:

```bash
curl --fail --show-error http://127.0.0.1:9091/greeting
```

Expected output is `Hello from environment variable`.

You can set env vars **for a single process only**:

```bash
SERVER_PORT=9092 APP_GREETING="Single-process configuration" ./target/native-demo
```

**PowerShell:**

```powershell
$env:SERVER_PORT = "9093"
$env:APP_GREETING = "Hello from PowerShell"

.\target\native-demo.exe

# Clean up variables in the PowerShell session after testing
Remove-Item Env:SERVER_PORT
Remove-Item Env:APP_GREETING
```

You do not have to declare placeholders in `application.yml`: Spring Boot already reads OS environment variables as a property source. However, if you want to map **an arbitrary env var name** to a property, you can use a placeholder:

```yaml
app:
  greeting: "${WELCOME_MESSAGE:Default hello}"
```

Here, `WELCOME_MESSAGE` provides the value for `app.greeting` if present; otherwise, Spring uses the fallback after `:`.

**Technical note:** env var mapping for loggers with long, case-sensitive package/class names is not always preserved because name normalization loses casing information. For detailed per-class logging configuration, prefer file-based configuration or an appropriately supported Spring Boot mechanism.

## 5. Method 3 — Using External Configuration Files

### 5.1. Why Is External Configuration Needed?

`src/main/resources/application.yml` is packaged into the application build. When building a Native Image, eligible resources are embedded into the artifact via AOT/native processing. **Editing the source YAML after building does not change the existing binary.**

In operations, you typically want one executable to run across multiple environments. Spring Boot allows reading `application.yml`, `application.properties`, and profile-specific variants from the **filesystem at startup**.

Example layout:

```text
/opt/native-demo/
  native-demo
  config/
    application.yml
```

External file contents:

```yaml
server:
  port: 9094

app:
  greeting: "Configuration from external file"

logging:
  level:
    root: INFO
```

By default, Spring Boot searches config locations relative to the working directory, including `./` and `./config/`. However, the working directory under systemd, Docker, or an IDE may differ from running in a terminal. To avoid depending on the working directory, specify the path explicitly.

### 5.2. `spring.config.additional-location`

To **add** an external config search location:

```bash
./target/native-demo \
  --spring.config.additional-location=optional:file:./config/
```

In this argument:

- `spring.config.additional-location` adds an external location on top of the standard locations.
- `file:./config/` is a path relative to the **process working directory**, not necessarily the binary's directory.
- The trailing `/` is required when specifying a **directory** so Spring Boot automatically looks for `application.yml` or `application.properties`.
- `optional:` allows startup if the location does not exist. **Do not use `optional:` for mandatory config files**, because a missing file would be silently ignored and the app would run with defaults.

To use an absolute path:

```bash
./target/native-demo \
  --spring.config.additional-location=file:/etc/native-demo/
```

Or use an environment variable instead of CLI:

```bash
export SPRING_CONFIG_ADDITIONAL_LOCATION="file:/etc/native-demo/"
./target/native-demo
```

Distinguish two commonly confused properties:

| Property | Behavior | When to use |
|---|---|---|
| `spring.config.additional-location` | **Adds** locations to the default config search paths | You have defaults in the binary and want external files to override specific properties |
| `spring.config.location` | **Replaces** default locations with the specified locations | You want exact control over every config source searched |

If you switch from `additional-location` to `location` without declaring properties that existed in the packaged file inside the external file, some default values may no longer be found. This is an operational difference worth verifying.

### 5.3. Profile-Based Configuration

For example, create `/etc/native-demo/application-prod.yml`:

```yaml
app:
  greeting: "Hello from prod configuration"

logging:
  level:
    root: WARN
```

Run:

```bash
./target/native-demo \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/native-demo/
```

Spring Boot loads config data for the active profile according to location and profile precedence rules. A single YAML file can also contain multiple documents separated by `---`:

```yaml
app:
  greeting: "Default value"

---
spring:
  config:
    activate:
      on-profile: prod

app:
  greeting: "Value for prod"
```

**Important for Spring AOT:** choosing a profile when running the binary can control runtime values like log levels, endpoints, or messages. However, annotations and conditions such as `@Profile` and `@ConditionalOnProperty` that alter the **set of beans** were typically already evaluated by Spring during AOT **at build time**. A binary does not dynamically instantiate new beans enabled solely by a new runtime profile. If changing a profile alters the application context topology, activate the matching profile during AOT and build/test a binary for that configuration.

## 6. Which Source Takes Precedence When Properties Collide?

Suppose `server.port` appears in four places. In this typical example, precedence from **highest to lowest** is:

| Source | Port value | Result when all sources are present |
|---|---:|---|
| Command line `--server.port=9100` | 9100 | **Selected** |
| Environment `SERVER_PORT=9090` | 9090 | Overridden by CLI |
| External config file loaded with higher priority | 8085 | Overridden by env/CLI |
| Config file packaged inside the app | 8080 | Default value |

These are just four common sources. Spring Boot also supports Java system properties, `SPRING_APPLICATION_JSON`, config imports, test property sources, and other specialized sources. Ordering among **config documents** is also affected by location, profile-specific files, and import order. Do not infer from this table that every external file always outranks every other source.

In particular, `spring.config.location`, `spring.config.additional-location`, and `spring.config.name` are evaluated **very early during config discovery**. Supply them via command line or environment variables rather than placing them inside a file Spring has not discovered yet.

### Testing Precedence with the Sample App

Keep the packaged `application.yml` with `server.port=8080` and `app.greeting="Packaged"`. Create `./config/application.yml`:

```yaml
server:
  port: 8085

app:
  greeting: "External file"
```

Run:

```bash
APP_GREETING="From environment" ./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --server.port=9100
```

Expect the application to serve at `http://127.0.0.1:9100/greeting` and return `From environment`. `server.port` comes from the CLI, while `app.greeting` comes from the environment. Each property is resolved **independently** from the highest-precedence source that defines it.

If you need to inspect config resolution during development:

```bash
./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --logging.level.org.springframework.boot.context.config=TRACE
```

TRACE logs trace each config data loading step, though they can be very verbose so enable them only for diagnostics.

## 7. The Boundary Between Runtime and Build-Time Configuration in Native Image

The most important difference in Spring Boot Native Image is that **the bean model has been partially pre-processed**. Not every runtime change can cause a native app to reconstruct its Spring context.

| Information Type | Changeable at runtime with the same binary? | Example |
|---|---|---|
| HTTP port | **Yes** | `SERVER_PORT=9090` |
| Endpoints, timeouts, credentials used by existing beans | **Generally yes** | `SPRING_DATASOURCE_URL`, secrets, business properties |
| Log levels | **Generally yes** | `LOGGING_LEVEL_ROOT=WARN` |
| Profiles changing **values** in config files | **Yes**, if not conflicting with AOT constraints | `application-prod.yml` changing a message |
| Profiles/conditions adding beans absent at AOT time | **Cannot be expected** | `@Profile("prod")` on a new `@Bean` |
| Adding JARs/plugins or dynamic classes from filesystem post-build | **No** in the flexible JVM classpath sense | Plugin present only after deploy |
| Modifying resources **embedded inside the binary** | **No** | Embedded templates/configs require rebuilding |
| Adding missing reflection/resource metadata | **Requires rebuilding** when hints must change | Feature failing only on a native runtime branch |

Example:

```java
@Profile("cloud")
@Bean
CloudStorageClient cloudStorageClient() {
    return new CloudStorageClient();
}
```

If this bean was not in the application context during the AOT build, merely setting `SPRING_PROFILES_ACTIVE=cloud` at runtime does not guarantee creating the new bean. By contrast, for a bean already compiled into the binary, changing an endpoint URL read from a runtime property is completely valid.

A helpful distinction:

- **Information deciding build-time structure:** bean set, `@Conditional`, certain profiles, dependencies, dynamically used classes, and packaged resources.
- **Runtime operational information:** ports, hosts, URLs, timeouts, log levels, secrets, and values that do not alter bean topology.

Separate these two categories before sharing a single binary across development, staging, and production environments.

## 8. Managing Secrets and Sensitive Configuration

**Do not put real passwords in CLI commands, source code, Dockerfiles, or compiled applications.** A native binary is not a secret vault: strings or resources embedded in an executable can be inspected and extracted.

For applications with a datasource, you can use environment variables injected via a secret manager or deployment platform:

```bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://db.internal:5432/orders"
export SPRING_DATASOURCE_USERNAME="orders_app"

# Password is provided separately by the environment's secret management mechanism.
./target/native-demo
```

The sample REST app in Section 2 **has no database dependency**; `SPRING_DATASOURCE_*` variables merely illustrate naming conventions for real projects using JDBC/DataSource.

Another option is mounting secrets as files and using **Spring Boot config trees**:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

For example, when the directory is mounted, the file `/run/secrets/spring.datasource.password` can supply the `spring.datasource.password` property. Use `optional:configtree:/run/secrets/` only if the app is allowed to run when the secrets directory is absent; do not turn a missing mandatory secret into a silent failure.

Even environment variables require restricted read access; avoid dumping the entire environment into logs or crash dumps. For HTTPS/TLS, verify read permissions on certificates/truststores and confirm the native binary/container has the required CA certificates.

## 9. Running the Native Binary in Docker

A container image packages the native process with a minimal OS userland; the container **does not change how Spring Boot resolves properties**.

Example Dockerfile for a **Linux** executable compiled for the matching architecture and using libraries satisfied by the base image:

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app

COPY target/native-demo /app/native-demo
RUN chmod 755 /app/native-demo

EXPOSE 8080
ENTRYPOINT ["/app/native-demo"]
```

The actual image must match architecture, libc, dynamic libraries, and certificates; configure a non-root user if required by deployment policy.

Build and run:

```bash
docker build -t native-demo:local .

docker run --rm \
  --name native-demo \
  -p 8081:8080 \
  -e SERVER_PORT=8080 \
  -e APP_GREETING="Hello from container" \
  native-demo:local
```

Verify from the host:

```bash
curl --fail --show-error http://127.0.0.1:8081/greeting
```

In this example, `8080` is **the port Spring Boot listens on inside the container** and `8081` is **the published host port**. The Dockerfile's `EXPOSE 8080` line is only metadata and does not publish a port on the host by itself.

Mounting an external config file in Bash:

```bash
docker run --rm \
  -p 8081:8080 \
  -v "$PWD/deploy-config:/config:ro" \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION="file:/config/" \
  native-demo:local
```

Place `deploy-config/application.yml` on the host so Spring Boot loads `/config/application.yml` inside the container. If the external file changes `server.port` to `9090`, the container must publish `-p 8081:9090`; to keep the old mapping, set `SERVER_PORT=8080` to override the file's port.

In Kubernetes, the same principles apply: use `env`, `ConfigMap`, `Secret`, or volume mounts and configure readiness probes. A container in `Running` state does not prove the app is actually ready to accept requests.

## 10. Launching via systemd or a Process Manager

A common pitfall is the **working directory**. The exact same `file:./config/` argument can resolve to different directories when run from a terminal, systemd, or a container.

Minimal Linux unit file example:

```ini
[Unit]
Description=Spring Boot Native Demo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nativeapp
WorkingDirectory=/opt/native-demo
Environment=SERVER_PORT=8080
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/native-demo/
ExecStart=/opt/native-demo/native-demo
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

The example assumes user `nativeapp` already exists, the binary has execute permission, and external config files have read permission. Its purpose is to highlight three elements: **`ExecStart` invokes the binary**, **`WorkingDirectory` is fixed**, and **configuration is passed via environment**.

For HTTP services, test graceful shutdown if in-flight requests must complete:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Test stopping the process with the appropriate signal on the target OS and verify actual timeouts; do not assume all connections finish cleanly when a container stops.

## 11. Common Errors

| Symptom | Possible Cause | Troubleshooting |
|---|---|---|
| `Permission denied` | Missing execute bit, inaccessible directory, or `noexec` mount | Check permissions and execution path |
| `Exec format error` | Binary built for wrong OS or CPU architecture | Build for the right target platform and architecture |
| Binary exists yet reports `No such file or directory` | Incompatible dynamic loader or system libraries | Check libc/loader and binary dependencies |
| Unexpected port | Property overridden by another source or wrong env var name | Inspect CLI, env, files, and startup logs |
| `Port already in use` | Another process holds the port | Pick a new port or stop the old process |
| External `application.yml` not found | Wrong working directory, path, read permission, or `optional:` masking it | Use an absolute path and omit `optional:` when required |
| Profile switched but beans are missing | Bean topology was resolved by Spring AOT at build time | Rebuild with the matching conditions/profile |
| JVM JAR works but native fails on template/serialization | Missing RuntimeHints/reflection/resources or incompatible library | Test actual flows on the binary, add hints, and rebuild |
| HTTPS fails in container | Missing CA certificates/truststore or required libraries | Check TLS, base image, and certificate paths |
| Container unreachable from host | Wrong `-p`, `server.port`, bind interface, or not ready yet | Verify internal port, port mapping, and readiness |

### Step-by-Step Diagnosis

**Step 1. Inspect the binary and environment.** On Linux:

```bash
ls -l ./target/native-demo
file ./target/native-demo
```

**Step 2. Run minimally on an isolated port.**

```bash
./target/native-demo --server.port=9191 --app.greeting="smoke-test"
```

**Step 3. Exercise real functionality.** In another terminal:

```bash
curl --fail --show-error --max-time 5 http://127.0.0.1:9191/greeting
```

**Step 4. Layer in configuration sources one at a time.** Test environment variables, then external files. Observe which properties get overridden. To trace which files are loaded, temporarily enable TRACE for `org.springframework.boot.context.config`.

**Step 5. If only native fails, test functionality on both JVM and native from the same commit.** Check branches relying on reflection, dynamic proxies, resources, TLS, JSON, and external connections. A successful build does not guarantee full compatibility.

## 12. Practice Exercise: One Executable, Three Configurations

The goal is **not rebuilding the binary** across three runs. Stop the previous run before starting the next.

**Run A — Default configuration:**

```bash
./target/native-demo
curl --fail --show-error http://127.0.0.1:8080/greeting
```

Expected: `Hello from default configuration`.

**Run B — Using environment variables:**

```bash
SERVER_PORT=9091 APP_GREETING="From env" ./target/native-demo
```

In another terminal, call `http://127.0.0.1:9091/greeting`. Expected: `From env`.

**Run C — Combining external file and command line:**

Create `./config/application.yml` with:

```yaml
server:
  port: 9092

app:
  greeting: "From external file"
```

Run:

```bash
./target/native-demo \
  --spring.config.additional-location=file:./config/ \
  --server.port=9093
```

The application must listen on **9093** because CLI overrides the external file's port; `/greeting` must return **From external file**. Also try adding `APP_GREETING="From env"` to verify that environment overrides that specific property.

### Recording Test Results

| Run | Primary config source | Expected port | `/greeting` response |
|---|---|---:|---|
| A | Packaged config | 8080 | Hello from default configuration |
| B | Environment | 9091 | From env |
| C | External file + CLI | 9093 | From external file |

After verifying runtime configuration, experiment with a `@Profile` affecting the bean set in a separate project and compare build-time vs. runtime behavior. This makes the AOT boundary tangible, preventing the misconception that "switching a profile" always means "changing the entire application structure" inside a native binary.

## 13. Deployment Checklist

- [ ] Binary is built for the target OS and CPU architecture and meets target system library requirements.
- [ ] Startup command invokes the right executable with execute permissions and valid path.
- [ ] CLI, OS environment, and external config are all verified against the **actual binary**.
- [ ] Config file paths use absolute paths when deployment environments alter the working directory.
- [ ] Mandatory config files fail fast if missing; `optional:` is not used to mask errors.
- [ ] Profiles/conditionals affecting bean topology were properly prepared during the AOT build.
- [ ] Secrets are never embedded in Git, logs, shell history, or the binary.
- [ ] Internal ports, Docker/Kubernetes mappings, health/readiness, and shutdown have been tested.
- [ ] Features using reflection/resources/TLS/databases have integration tests on the native executable.
- [ ] When comparing against the JVM build, startup-to-**readiness** time and actual RAM are measured under the same workload; binary file size is not mistaken for runtime memory usage.

## 14. Summary

A Spring Boot Native Image application still uses familiar **externalized configuration** mechanisms: `--property=value` flags, environment variables like `SERVER_PORT`, profile-based `application.yml` files, and external locations. These allow running a single binary across environments that share the same bean model, avoiding rebuilds just to change a port, URL, or log level.

The core limitation is that **Spring AOT already processed part of the application structure at build time**. Changing runtime values does not equate to changing the classpath, selected beans, or compiled hints. Therefore, verify both the effective properties at startup and run smoke and integration tests on the native binary before deployment.

### References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot Reference — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/reference/packaging/native-image/developing-your-first-application.html)
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
