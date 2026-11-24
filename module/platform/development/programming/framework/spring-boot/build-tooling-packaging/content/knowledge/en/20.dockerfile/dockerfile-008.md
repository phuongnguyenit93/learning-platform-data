# Choosing Exec-Form ENTRYPOINT and Passing JVM Options at Runtime

## 1. Context: A Dockerfile Governs More Than Just the Launch Command

A Spring Boot application packaged as an executable JAR runs directly on a developer machine:

~~~bash
java -Xms64m -Xmx256m -Ddemo.jvm.tag=local -jar target/runtime-probe-1.0.0.jar --app.mode=local
~~~

Once containerized, however, that command becomes the image's **startup contract**: Docker must know what the main process is, which arguments it accepts, how it handles `SIGTERM`, and whether operators can adjust JVM/application settings without rebuilding the image.

This lesson focuses on **choosing exec-form `ENTRYPOINT` and passing JVM options at runtime**. Do not conflate:

- **Build command:** `RUN` in the Dockerfile executes during image build time.
- **Startup command:** `ENTRYPOINT` runs when a container is created.
- **Default arguments:** `CMD` appends default arguments to an exec-form `ENTRYPOINT`, and can be overridden by trailing arguments after the image name in `docker run`.
- **JVM options:** `-Xmx`, `-Xms`, `-XX:...`, `-D...` are inputs to the Java launcher/VM and must appear **before `-jar`** if passed on the Java command line.
- **Application arguments:** `--server.port=...`, `--spring.profiles.active=...`, `--app.mode=...` are arguments after the JAR handled by Spring Boot.
- **Environment variables:** `JDK_JAVA_OPTIONS` and `JAVA_TOOL_OPTIONS` are supported by the JDK; `JAVA_OPTS` is merely a convention used by certain entrypoint scripts or launchers and **is not read automatically by Java by default**.

After this lesson, you will know when to pick the JSON-array exec form, why shell form causes signal/argument forwarding bugs, how to set `CMD`, how to pass JVM flags at runtime while preserving exec form, how to inspect inside the container, along with a runnable Spring Boot 4.1.2 / Java 17 example and common safety/operational pitfalls.

## 2. How Do Exec Form and Shell Form Differ?

Docker supports two syntaxes for `ENTRYPOINT` and `CMD`. They differ fundamentally in **how Docker spawns the process**.

### 2.1. Exec form — the recommended default

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is a **JSON array**. Docker invokes executable `java` with each argument separated:

~~~text
argv[0] = "java"
argv[1] = "-jar"
argv[2] = "/app/app.jar"
~~~

Advantages:

1. **Does not implicitly invoke `/bin/sh -c`.** Java becomes the container's main process when no init wrapper is added, making signal delivery from Docker cleaner.
2. No shell word splitting, variable expansion, globbing, or unintended pipelines.
3. Easy to audit: each argument is an explicit JSON element with no nested shell quoting to reason about.
4. Combines cleanly with `CMD ["--server.port=8080"]` to pass default application arguments.
5. Compatible with container runtime models and orchestrators that override `command`/`args`.
6. Avoids a parent shell sitting at PID 1 and failing to forward `SIGTERM` to the child JVM.

**JSON syntax:** use **double quotes**, never single quotes; each token must be its own array element. For example, `["java", "-Xmx256m", "-jar", "/app/app.jar"]` is valid, whereas `["java -Xmx256m -jar /app/app.jar"]` tries to invoke an executable whose literal filename contains the whole string, which fails.

### 2.2. Shell form — shorter, with consequences

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

On Linux, Docker typically runs the equivalent of:

~~~text
/bin/sh -c "java -jar /app/app.jar"
~~~

When the shell holds PID 1, the JVM runs as a **child process**. Shells do not automatically forward all signals to child processes; `docker stop` sends `SIGTERM` to the main process, so the Java application may never receive the stop request cleanly and instead be force-killed after the grace period.

Adding `exec` to shell form:

~~~dockerfile
ENTRYPOINT exec java -jar /app/app.jar
~~~

makes the shell **replace itself with the JVM**, partially solving the PID 1 issue. Still, Docker's shell-form `ENTRYPOINT` has awkward semantics when combined with `CMD` and trailing `docker run` arguments. **Do not choose shell form merely to pass JVM flags via environment variables**; Section 7 presents a safer and simpler approach.

### 2.3. Comparison Table

| Aspect | Exec Form | Shell Form |
| --- | --- | --- |
| Dockerfile | `ENTRYPOINT ["java","-jar","/app/app.jar"]` | `ENTRYPOINT java -jar /app/app.jar` |
| Automatic shell? | **No** | **Yes** (`/bin/sh -c` on Linux) |
| PID 1 (without init) | Directly Java | Typically the shell |
| `CMD`/runtime args | Appended to exec ENTRYPOINT | Often ignored per shell ENTRYPOINT semantics |
| `$VAR` variables in command | **Not** expanded automatically | Shell may expand |
| Shutdown signals | Java receives signals more directly | Parent shell may not forward |
| Auditability | Explicit JSON elements | Depends on shell parsing/quoting |
| Recommendation for Spring Boot | **Preferred** | Only when a shell is truly needed and consequences are understood |

**Do not overclaim:** exec form **does not automatically guarantee** graceful shutdown if the app ignores signals, deadlocks, or has too short a grace period. It removes a common barrier preventing signals from reaching the JVM, rather than replacing shutdown testing.

## 3. JVM Options Must Come Before `-jar`

Java 17 command syntax is:

~~~text
java [JVM/launcher options] -jar <executable-jar-file> [application arguments]
~~~

**Correct** example:

~~~bash
java -Xms64m -Xmx256m -Ddemo.jvm.tag=from-command -jar app.jar --app.mode=blue
~~~

Breakdown:

| Token | Who Parses It? | Meaning |
| --- | --- | --- |
| `-Xms64m` | JVM | Initial heap hint of 64 MiB |
| `-Xmx256m` | JVM | Maximum heap limit of 256 MiB |
| `-Ddemo.jvm.tag=from-command` | JVM | Java system property named `demo.jvm.tag` |
| `-jar app.jar` | Java launcher | Selects the executable JAR |
| `--app.mode=blue` | Spring Boot / application | Spring runtime configuration |
| `--server.port=9090` | Spring Boot / application | Internal server port |

Syntax that **does not work as intended**:

~~~bash
java -jar app.jar -Xmx256m
~~~

Placed after the JAR file, `-Xmx256m` is passed by the Java launcher to `main(String[] args)` as an **application argument**. The Java launcher no longer interprets it as a heap limit. A framework may parse or ignore that string according to its own rules; **never** claim the JVM accepted the flag just because the container started.

Similarly, with:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["-Xmx256m"]
~~~

`CMD` is appended **after** `/app/app.jar`, so this **is not** how to configure JVM heap. Use Java-supported environment variables, put fixed flags before `-jar`, or use a wrapper script with `exec`.

### `-D` Differs from `--`

- `-Dspring.profiles.active=prod` (before `-jar`): Java system property added to JVM system properties; Spring Boot can read it.
- `--spring.profiles.active=prod` (after `.jar`): command-line property Spring Boot reads from application arguments.
- `SPRING_PROFILES_ACTIVE=prod`: environment variable Spring Boot can read, not a JVM option.
- `-Ddemo.jvm.tag=...`: verified via `System.getProperty("demo.jvm.tag")`.
- `--app.mode=...`: verified via Spring `Environment#getProperty("app.mode")`.

Do not mix up configuration sources. If the same key is supplied in multiple sources, Spring Boot applies its precedence order; do not evaluate one flag's effect when a higher-precedence source overrides it.

## 4. `ENTRYPOINT` Combined with `CMD` and `docker run`

Dockerfile:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

Running:

~~~bash
docker run --rm example-app:1.0
~~~

Docker launches the equivalent of:

~~~text
java -jar /app/app.jar --server.port=8080
~~~

Running:

~~~bash
docker run --rm example-app:1.0 --server.port=9090 --app.mode=green
~~~

replaces **all default `CMD` elements** with the arguments trailing the image name. Equivalent process:

~~~text
java -jar /app/app.jar --server.port=9090 --app.mode=green
~~~

This is why `CMD` should hold **overridable default arguments**. When the goal is passing app args while keeping Java as the entrypoint, exec form is a clean design.

### The `docker run` Argument Ordering Trap

General syntax:

~~~text
docker run [Docker options] IMAGE [COMMAND or arguments...]
~~~

Example:

~~~bash
docker run --rm -p 18080:8080 -e APP_MODE=blue example-app:1.0
~~~

`-p` and `-e` are **Docker options**, so they must appear before the image name. Placing them **after** `example-app:1.0` causes Docker to pass them to `ENTRYPOINT` as app arguments rather than interpreting them as Docker flags.

Likewise, `--server.port` after the image is an **app argument**; `-Xmx256m` after the image is also just an **app argument**. To give the JVM `-Xmx` at runtime, use `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` or intentionally override the exec command.

### When Is `CMD` Unnecessary?

If all runtime Spring Boot configuration comes from `application.properties`, environment variables, or external config, you can simply declare:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Omitting `CMD` does not prevent passing trailing arguments after the image name. `CMD` provides **defaults**, not a mandatory part of an entrypoint.

## 5. Complete Spring Boot 4.1.2 and Java 17 Example

To verify exactly what the JVM receives versus what Spring Boot receives, we expose an HTTP endpoint with deterministic output. The example avoids relying on JVM logs, startup ordering, or memory metrics that vary by host.

### 5.1. Project structure

~~~text
runtime-probe/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/
│   ├── main/
│   │   ├── java/dev/example/runtime/
│   │   │   ├── RuntimeProbeApplication.java
│   │   │   └── ProbeText.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/dev/example/runtime/ProbeTextTest.java
└── target/              # created by Maven, holds executable JAR
~~~

### 5.2. `pom.xml`

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
    <artifactId>runtime-probe</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The starter parent configures Maven Plugin `repackage` to produce the Spring Boot executable JAR during the `package` phase. `spring-boot-starter-webmvc` provides Spring MVC and the embedded servlet server for the HTTP example; `spring-boot-starter-test` supplies JUnit Jupiter at test scope. Java 17 is the minimum compatible version for Spring Boot 4.1.2.

### 5.3. `src/main/java/dev/example/runtime/ProbeText.java`

~~~java
package dev.example.runtime;

public final class ProbeText {
    private ProbeText() {
    }

    public static String render(String jvmTag, String appMode) {
        return "jvmTag=" + jvmTag + ";appMode=" + appMode;
    }
}
~~~

This class uses only Java SE. Isolating formatting logic in a pure Java class lets unit tests run without starting a web server.

### 5.4. `src/main/java/dev/example/runtime/RuntimeProbeApplication.java`

~~~java
package dev.example.runtime;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class RuntimeProbeApplication {

    private final Environment environment;

    public RuntimeProbeApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(RuntimeProbeApplication.class, args);
    }

    @GetMapping("/probe")
    public String probe() {
        String jvmTag = System.getProperty("demo.jvm.tag", "unset");
        String appMode = environment.getProperty("app.mode", "default");
        return ProbeText.render(jvmTag, appMode);
    }

    @PreDestroy
    public void onShutdown() {
        System.out.println("APP_CONTEXT_CLOSED");
    }
}
~~~

**Two values supplied from two different sources:**

- `jvmTag` reads a **Java system property**; to set it via the Java launcher, pass `-Ddemo.jvm.tag=...` before `-jar` or use a supported Java environment variable.
- `appMode` reads the **Spring Environment**; `--app.mode=...` after `.jar` or environment variable `APP_MODE` can supply it.
- `@PreDestroy` prints `APP_CONTEXT_CLOSED` when the bean is destroyed as the Spring context closes. This is a useful indicator for `docker stop` experiments, **not a guarantee** if the process hits `SIGKILL`, power loss, or shutdown hooks run out of time.
- `GET /probe` returns the **HTTP response body**, not Java process stdout.

### 5.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=runtime-probe
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
~~~

`server.shutdown=graceful` allows the web server to drain in-flight requests per Spring Boot shutdown policy; the 20-second timeout governs **Spring shutdown phases** and does not replace Docker's stop timeout. Pair a **container grace period** long enough for your application limit; multiple phases or slow requests can extend shutdown duration.

### 5.6. `src/test/java/dev/example/runtime/ProbeTextTest.java`

~~~java
package dev.example.runtime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProbeTextTest {
    @Test
    void rendersSeparateJvmAndAppInputs() {
        assertEquals(
                "jvmTag=from-env;appMode=blue",
                ProbeText.render("from-env", "blue")
        );
    }
}
~~~

This test checks output formatting, **not whether Docker/ENTRYPOINT picks up environment variables**. Verify that against the built image.

### 5.7. Build the JAR Before Creating the Image

~~~bash
java -version
mvn -version
mvn clean verify
jar tf target/runtime-probe-1.0.0.jar
~~~

The archive should contain `BOOT-INF/classes/dev/example/runtime/RuntimeProbeApplication.class`, `BOOT-INF/classes/dev/example/runtime/ProbeText.class`, and matching dependencies in `BOOT-INF/lib`. Do not pick `*.jar.original` for deployment if the Spring Boot plugin keeps a backup of the ordinary JAR.

Test directly outside Docker:

~~~bash
java -Ddemo.jvm.tag=local -jar target/runtime-probe-1.0.0.jar --server.port=18080 --app.mode=local
~~~

In another terminal:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

**Exact HTTP response body:**

~~~text
jvmTag=local;appMode=local
~~~

Stop the process with `Ctrl+C`. This baseline confirms the Java code and app config work before adding Docker layers.

## 6. Default Dockerfile: Exec ENTRYPOINT and App CMD

File **`Dockerfile`**:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY --chown=10001:10001 target/runtime-probe-1.0.0.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

**Explanation:**

1. `FROM eclipse-temurin:17-jre` picks a Java 17 runtime. Production should **pin the image by digest** per policy so tags do not drift over time.
2. `WORKDIR /app` sets the working directory, without affecting classpath resources inside the Boot JAR.
3. `COPY --chown=10001:10001` copies the **Maven-built artifact** into the image rather than copying the source tree.
4. `USER 10001:10001` runs as non-root (an illustrative numeric UID/GID). Port 8080 is unprivileged. Real containers still need permission checks on any writable folders.
5. `EXPOSE 8080` serves as informational metadata for the app port; **does not publish the port to the host**.
6. Exec-form `ENTRYPOINT` keeps `java` as the main process when running without an init wrapper.
7. `CMD` holds **default Spring Boot arguments**, appended after `/app/app.jar` and overridable at `docker run`.

File **`.dockerignore`** for this prebuilt-artifact example:

~~~text
.git
.idea
.vscode
src
target/classes
target/test-classes
target/surefire-reports
target/*.jar.original
*.log
~~~

**Caution:** do not put `target` or `target/*.jar` in `.dockerignore` because that would exclude `target/runtime-probe-1.0.0.jar` from the build context and cause `COPY` to fail. In real pipelines, use a multi-stage build or a context containing only the output artifact to avoid leaking build details.

### Build the Docker Image

From the directory containing `Dockerfile` after `mvn clean verify` succeeds:

~~~bash
docker build -t runtime-probe:1.0.0 .
~~~

Do not run `docker build` before the JAR exists. `COPY` reads `target/runtime-probe-1.0.0.jar`, so the Maven artifact must already exist unless the Dockerfile adds its own build stage (omitted in this focused example).

## 7. Passing JVM Flags via `JDK_JAVA_OPTIONS` — Simple Way While Keeping Exec Form

**`JDK_JAVA_OPTIONS` is an environment variable supported by the Java launcher since JDK 9**, including Java 17. The launcher reads it and **prepends its options onto the Java command line**, letting you pass `-Xms`, `-Xmx`, and `-D` without shell word splitting in the Dockerfile.

From the host terminal:

~~~bash
docker run --rm --name runtime-probe-env \
  --memory=512m \
  -p 18081:8080 \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m -Ddemo.jvm.tag=from-env' \
  runtime-probe:1.0.0 \
  --server.port=8080 --app.mode=blue
~~~

The Java process spawned by exec `ENTRYPOINT` is still:

~~~text
java -jar /app/app.jar --server.port=8080 --app.mode=blue
~~~

Yet the **Java launcher** reads `JDK_JAVA_OPTIONS` and applies JVM options equivalent to:

~~~text
java -Xms64m -Xmx256m -Ddemo.jvm.tag=from-env \
     -jar /app/app.jar --server.port=8080 --app.mode=blue
~~~

This illustrates **launcher semantics**, not Docker rewriting the `ENTRYPOINT` JSON array.

Another terminal:

~~~bash
curl -fsS http://127.0.0.1:18081/probe
~~~

**Exact HTTP response body:**

~~~text
jvmTag=from-env;appMode=blue
~~~

**Preconditions:** host port 18081 is free, container port 8080 is listening, and no higher-precedence config source overrides `app.mode` or `demo.jvm.tag`.

### Points to Remember

- `JDK_JAVA_OPTIONS` is not **shell variable expansion** in the Dockerfile; it is read by the **Java launcher itself**.
- The Java launcher may print a notice to **stderr** like `NOTE: Picked up JDK_JAVA_OPTIONS: ...`. That line is not a JVM error.
- This variable **cannot replace `-jar` or the main class**. The Java launcher rejects launcher-control flags like `-jar` or `-h` inside `JDK_JAVA_OPTIONS`.
- If passing values with spaces in `-D...`, consult the Java launcher's quoting rules rather than assuming shell and launcher parse quotes identically. Prefer simple option values or an explicit config file.
- Never place secrets in `JDK_JAVA_OPTIONS`; they can be exposed in container configs, logs, diagnostics, or admin tools.
- `--memory=512m` caps **container memory**, which does not mean `-Xmx256m` uses all of it. The JVM also needs metaspace, thread stacks, code cache, and native memory. Account for JVM and app overhead to avoid OOMs.

### Dockerfile with Default JVM Options

You can give the image a non-secret JVM baseline:

~~~dockerfile
ENV JDK_JAVA_OPTIONS="-XX:MaxRAMPercentage=70.0 -Dfile.encoding=UTF-8"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

If runtime passes `-e JDK_JAVA_OPTIONS=...`, the runtime environment value **replaces** the image default. Do not assume Docker concatenates option strings. If both sets of flags must be preserved, enforce a clear policy and merge them at configuration time.

**`-XX:MaxRAMPercentage=70.0`** sizes heap as a percentage of memory when no explicit heap override like `-Xmx` is set; actual sizing depends on Java/cgroup detection and other JVM flags. Never claim 70% of container memory represents all memory Java can consume.

## 8. `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and `JAVA_OPTS`

Three names are easily confused, yet **they are not the same**:

| Variable | Read By | Works with Exec ENTRYPOINT? | Notes |
| --- | --- | --- | --- |
| `JDK_JAVA_OPTIONS` | `java` launcher | **Yes** | Prepends launcher options; rejects launcher controls like `-jar` |
| `JAVA_TOOL_OPTIONS` | JVM/JNI initialization (when supported) | **Yes** | Suits VM/agent flags; cannot set main class or JAR target |
| `JAVA_OPTS` | **Not a standard Java launcher variable** | **Not automatically** | Works only if a wrapper/buildpack/entrypoint **explicitly** reads it |
| `APP_MODE` | Spring Boot environment resolver | Yes | **Application config**, not a JVM flag |
| `SPRING_PROFILES_ACTIVE` | Spring Boot environment resolver | Yes | Selects Spring profile, not `-Xmx` |

### 8.1. Using `JAVA_TOOL_OPTIONS`

Example:

~~~bash
docker run --rm --name runtime-probe-tool \
  -p 18082:8080 \
  -e JAVA_TOOL_OPTIONS='-Ddemo.jvm.tag=from-tool -Xmx256m' \
  runtime-probe:1.0.0 --server.port=8080 --app.mode=tool
~~~

Another terminal:

~~~bash
curl -fsS http://127.0.0.1:18082/probe
~~~

Body:

~~~text
jvmTag=from-tool;appMode=tool
~~~

The JVM typically prints `Picked up JAVA_TOOL_OPTIONS: ...` to stderr. It affects **every JVM process** launched in that environment, including auxiliary Java tools inside the container. Therefore, do not assume it applies only to one Boot app if a container invokes multiple Java commands.

**Scope:** never put `-jar app.jar` into `JAVA_TOOL_OPTIONS`; selecting the application belongs to the Java launcher/`ENTRYPOINT`, not a VM option.

### 8.2. `JAVA_OPTS` Is a Convention, Not a Java Standard

The following **will not configure heap** on our image:

~~~bash
docker run --rm -e JAVA_OPTS='-Xmx256m' runtime-probe:1.0.0
~~~

With `ENTRYPOINT ["java","-jar","/app/app.jar"]`, the Java launcher **ignores `JAVA_OPTS`**. If another image uses an entrypoint script or buildpack that reads it, behavior differs; check that image's documentation.

Also **incorrect**:

~~~dockerfile
ENTRYPOINT ["java", "$JAVA_OPTS", "-jar", "/app/app.jar"]
~~~

Because exec form skips shell expansion, Java receives the literal string `"$JAVA_OPTS"` as an argument. When you want runtime-configurable JVM flags without complex shell logic, `JDK_JAVA_OPTIONS` is simpler and easier to test.

## 9. Hardcoding Fixed Flags in Exec ENTRYPOINT

When a product uses one fixed set of JVM flags, you can write them directly:

~~~dockerfile
ENTRYPOINT [
  "java",
  "-XX:MaxRAMPercentage=70.0",
  "-Dfile.encoding=UTF-8",
  "-jar",
  "/app/app.jar"
]
CMD ["--server.port=8080"]
~~~

**Every JVM flag appears before `-jar`**, and `CMD` sits after the JAR, preserving proper classification. Note that JSON syntax in a Dockerfile exec form **must be parsed cleanly as one instruction by the Dockerfile parser**. To avoid parser differences with line breaks, the most portable form is single-line:

~~~dockerfile
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=70.0", "-Dfile.encoding=UTF-8", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

Pros: easy to audit and zero env parsing. Cons: changing JVM flags requires **rebuilding the image** or overriding the entire entrypoint, making it best for a stable baseline.

### Do Not Use `CMD` for JVM Flags After `-jar`

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["-Xms64m", "-Xmx256m"]
~~~

In this pairing, Docker appends both tokens at the **end**:

~~~text
java -jar /app/app.jar -Xms64m -Xmx256m
~~~

Those become **application arguments**, not Java VM flags. This bug is easy to miss because Spring Boot often boots normally anyway; only checking actual JVM heap settings reveals the flags were ignored.

## 10. When an Entrypoint Script Is Truly Needed: Use `exec` and `"$@"`

Sometimes a container must prepare a certificate truststore, verify file permissions, create temp directories, or select among Java launch modes. In that case, use a **script as the executable in an exec-form ENTRYPOINT**:

File **`entrypoint.sh`**:

~~~sh
#!/bin/sh
set -eu

# Perform small, controlled preparation if needed.
# Never log secrets or construct shell commands with eval.
exec java -XX:MaxRAMPercentage=70.0 -jar /app/app.jar "$@"
~~~

Dockerfile variant:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --chown=10001:10001 target/runtime-probe-1.0.0.jar /app/app.jar
COPY --chown=10001:10001 entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--server.port=8080"]
~~~

**Why this preserves good behavior:**

- Docker uses exec form to invoke the script. Starting with `#!/bin/sh`, the OS runs the shell interpreter on it.
- `exec java ...` **replaces the shell with Java**, avoiding a shell holding PID 1 and blocking `SIGTERM`.
- `"$@"` forwards each argument from `CMD` or `docker run IMAGE ...` **preserving exact token boundaries**, critical if any argument contains spaces.
- `set -eu` halts the script on unhandled command errors or unset variables. It does not replace proper logging and observability.
- Fixed JVM flags precede `-jar`, while app args follow `/app/app.jar`.
- The script needs Linux-compatible line endings (`LF`) and execute permission; saving with CRLF triggers `/bin/sh^M: not found`.
- Do not add an entrypoint script just to pass `-Xmx`; `JDK_JAVA_OPTIONS` already solves that.

### Why Is `eval java $JAVA_OPTS ...` Discouraged?

Patterns like:

~~~sh
eval "java $JAVA_OPTS -jar /app/app.jar $*"
~~~

destroy argument boundaries, re-evaluate shell metacharacters, and introduce command-injection risk if `JAVA_OPTS` incorporates untrusted input. That is an **anti-pattern** and must not be used in startup scripts. Even `java $JAVA_OPTS -jar ...` without `eval` suffers unquoted word splitting/globbing and breaks arguments with spaces.

**Safer options:** use `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` for JVM flags, forward app args with `"$@"`, and stick to exec form. If policy mandates a launcher reading `JAVA_OPTS`, implement explicit parsing and allowlisting rather than assembling a raw shell command.

## 11. Verifying `ENTRYPOINT`, `argv`, and JVM Settings

### 11.1. Inspecting Image Configuration

~~~bash
docker image inspect runtime-probe:1.0.0 \
  --format 'ENTRYPOINT={{json .Config.Entrypoint}} CMD={{json .Config.Cmd}}'
~~~

Expected values matching Section 6's Dockerfile:

~~~text
ENTRYPOINT=["java","-jar","/app/app.jar"] CMD=["--server.port=8080"]
~~~

This reflects the **image configuration**, not runtime overrides. Using `docker run --entrypoint` changes the container's entrypoint from the image default. If a tool escapes spaces or formats JSON differently, verify the actual JSON elements rather than matching spacing rigidly.

### 11.2. Inspecting the Java Process

While the container is running:

~~~bash
docker top runtime-probe-env
~~~

On Linux you can read `/proc/1/cmdline` if the base image includes a shell and `tr`:

~~~bash
docker exec runtime-probe-env sh -c 'tr "\000" " " < /proc/1/cmdline'
~~~

Expected without an init wrapper: PID 1 is `java` with `-jar /app/app.jar` and the passed application arguments. **`JDK_JAVA_OPTIONS` may not appear in `/proc/1/cmdline`**, because it is an environment variable read by the Java launcher rather than a Docker command-line argument. Verify environment variables and JVM behavior directly rather than treating `/proc/1/cmdline` as sole proof that `-Xmx` took effect.

In a JRE-only image, do not assume `jcmd` exists; use a JDK diagnostic image, JVM metrics, Actuator/JMX, or approved observability tools for deeper inspection.

### 11.3. Verifying System and App Properties via the Endpoint

With a container started with:

~~~bash
-e JDK_JAVA_OPTIONS='-Ddemo.jvm.tag=from-env' \
runtime-probe:1.0.0 --app.mode=blue
~~~

the demo endpoint returns:

~~~text
jvmTag=from-env;appMode=blue
~~~

This proves Java received `-Ddemo.jvm.tag` and Spring Boot received `--app.mode`. It **does not** prove the active `-Xmx` heap size. To check heap limits, inspect JVM `MaxHeapSize`/`Runtime.maxMemory()` or run diagnostics on a compatible JVM, accounting for overhead and JVM rounding.

## 12. Testing `docker stop`, PID 1, and Graceful Shutdown

Docker sends `SIGTERM` to the main process on `docker stop`; after a grace period, a surviving process receives `SIGKILL`. With JSON-array exec `ENTRYPOINT`, Java receives the signal directly and Spring Boot gets a chance to close the web server and context cleanly.

### Experiment

Terminal 1:

~~~bash
docker run --rm --name runtime-probe-stop \
  -p 18083:8080 \
  runtime-probe:1.0.0
~~~

Terminal 2:

~~~bash
curl -fsS http://127.0.0.1:18083/probe
docker stop --time 25 runtime-probe-stop
~~~

After `docker stop`, check logs:

~~~bash
docker logs runtime-probe-stop
~~~

**Note on `--rm`:** the container may be deleted immediately upon stopping, making `docker logs runtime-probe-stop` fail. To **preserve logs after stop** during testing, run **without `--rm`**:

~~~bash
docker run --name runtime-probe-stop-qa -p 18083:8080 runtime-probe:1.0.0
~~~

Another terminal:

~~~bash
docker stop --time 25 runtime-probe-stop-qa
docker logs runtime-probe-stop-qa
docker rm runtime-probe-stop-qa
~~~

If graceful shutdown finishes cleanly, application logs may show the line from `@PreDestroy`:

~~~text
APP_CONTEXT_CLOSED
~~~

This is **evidence that the app closed its Spring context**, not a guarantee that sending `SIGTERM` always prints it. Certain versions, configs, or load conditions can still time out; check exit status, shutdown logs, and live behavior. The 25-second Docker stop timeout here is chosen above the 20-second shutdown phase as an illustration, not a universal number for all apps.

### Is `--init` Needed?

For images spawning multiple child processes that require zombie reaping, Docker provides:

~~~bash
docker run --init --rm -p 18084:8080 runtime-probe:1.0.0
~~~

`--init` inserts a lightweight init process at PID 1 to forward signals and reap child processes. In that mode, **Java is no longer PID 1**, yet remains the managed application process. Therefore, "exec form always makes Java PID 1" holds **only when no init wrapper or process supervisor is present**.

**Recommendation:** for single-process Spring Boot apps, exec `ENTRYPOINT` is clean and usually sufficient. Use `--init` when child processes require reaping; avoid applying one rigid rule to every image.

## 13. When to Hardcode JVM Flags vs Pass at Runtime?

| Requirement | Appropriate Approach | Notes |
| --- | --- | --- |
| Every deployment needs identical flag | Direct flag in exec `ENTRYPOINT` | Easy to audit, though changing flags requires rebuilding the image |
| Environments have different memory limits | `JDK_JAVA_OPTIONS` | Preserves exec form without a shell |
| JVM needs agent/diagnostic options supported by env | `JAVA_TOOL_OPTIONS` | Check blast radius and security |
| Need to switch Spring profile or port | `--spring.profiles.active`, `--server.port` after image; or Spring env vars | Application configuration, not JVM flags |
| Need filesystem setup before Java starts | Script ending with `exec java ... "$@"` | Preserves signal forwarding and argument boundaries |
| Existing platform launcher uses `JAVA_OPTS` | Follow that launcher's docs | Do not assume Java reads `JAVA_OPTS` natively |
| Raising heap due to container OOM | Check memory limit + native overhead, then tune JVM | `-Xmx` must never equal total container memory |
| Changing VM options without rebuilding image | Java runtime env or full entrypoint override | Never put JVM flags in `CMD` after `-jar` |

### Sizing Heap Inside a Container

An intentional example:

~~~bash
docker run --rm --memory=512m \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m' \
  -p 18085:8080 runtime-probe:1.0.0
~~~

The JVM consumes additional memory outside the heap for native allocations. Never set `-Xmx512m` in a `--memory=512m` container assuming enough room remains for metaspace, stacks, and GC. Monitor RSS, heap, memory cgroup stats, OOM kill events, and real workload load.

The interaction between `-Xmx`, `-XX:MaxRAMPercentage`, and memory limits also depends on other JVM options; no single percentage fits every service.

## 14. Docker Compose and Kubernetes: Putting Configuration in the Right Place

### 14.1. Docker Compose

Illustrative **`compose.yaml`** for Section 6's image:

~~~yaml
services:
  runtime-probe:
    image: runtime-probe:1.0.0
    ports:
      - "18080:8080"
    environment:
      JDK_JAVA_OPTIONS: "-Xms64m -Xmx256m -Ddemo.jvm.tag=compose"
    command:
      - "--server.port=8080"
      - "--app.mode=compose"
    stop_grace_period: 25s
~~~

In Docker Compose, `command` **overrides `CMD`**, not `ENTRYPOINT`. `--server.port`/`--app.mode` append after `-jar` thanks to the image's exec `ENTRYPOINT`. `environment` passes JVM options to the Java launcher before the main class starts.

Run:

~~~bash
docker compose up
~~~

When the app is ready:

~~~bash
curl -fsS http://127.0.0.1:18080/probe
~~~

Body:

~~~text
jvmTag=compose;appMode=compose
~~~

Stop with `docker compose down`. For production, add restart policies, health/readiness checks, resources, and secrets per operational policy. Never commit sensitive keys in Compose YAML.

### 14.2. Kubernetes

In Kubernetes, for a container image with an exec `ENTRYPOINT`:

- Container `command` **overrides the image `ENTRYPOINT`**.
- Container `args` **override the image `CMD`**.
- `env` sets process environment variables before the Java launcher starts.

Illustrative fragment inside `containers:`:

~~~yaml
- name: runtime-probe
  image: runtime-probe:1.0.0
  env:
    - name: JDK_JAVA_OPTIONS
      value: "-Xms64m -Xmx256m -Ddemo.jvm.tag=k8s"
  args:
    - "--server.port=8080"
    - "--app.mode=k8s"
  ports:
    - containerPort: 8080
~~~

This **is not a full Deployment manifest**; it only illustrates the mapping. Because `command` is omitted, Kubernetes keeps the image's `ENTRYPOINT` while `args` replaces the default `CMD`. Real deployments need a Pod template, resource requests/limits, probes, termination grace period, security context, and image pull policy per environment.

If you do override `command` to `["java","-jar","/app/app.jar"]`, ensure any direct JVM flags come **before `-jar`**, leaving `args` for app config afterward.

## 15. Security and Repeatability of Runtime Configuration

1. **Never put secrets into JVM args or default Docker `ENV`** where they can leak via image layers, diagnostics, container inspection, logs, or process metadata. Use a secret manager or volume injection so the app reads secrets from protected sources.
2. **Do not run as root** unnecessarily. Verify JAR read permissions, `/tmp` and log directory write permissions, and port bindings when using a numeric UID/GID without a named user.
3. **Pin base image digests** for reproducible, reviewable releases rather than relying on a mutable tag.
4. **Do not mix build-time and runtime options.** `MAVEN_OPTS`/`GRADLE_OPTS` on the build host do not configure the container's runtime `java -jar` JVM.
5. **Never use `eval` or concatenate untrusted flags into shell commands.** Doing so risks injection, word splitting, and altered argument semantics.
6. **Never dump all environment variables or JVM args on a public HTTP endpoint.** The demo `/probe` exposes a dummy non-sensitive property for teaching only. In production, restrict or remove debug endpoints.
7. **Prevent uncontrolled runtime application config changes.** `--app.mode` is an example; production profiles, ports, and resources require IaC and change review.
8. **Separate build artifacts from operations:** the same immutable image can run across dev, staging, and prod with appropriate env/args. Record the release image digest and deployment config separately for auditing.

## 16. Troubleshooting Table

| Symptom | Cause | Check and Fix |
| --- | --- | --- |
| `exec: "java -jar /app/app.jar": executable file not found` | Whole command written as one JSON string | `ENTRYPOINT ["java","-jar","/app/app.jar"]` |
| Dockerfile exec form fails to expand `$JAVA_OPTS` | Exec form skips shell | Use `JDK_JAVA_OPTIONS` or a proper wrapper script |
| Heap unchanged despite `CMD ["-Xmx..."]` | Flag placed **after `-jar`** | Move before `-jar` or into `JDK_JAVA_OPTIONS` |
| App ignores `--app.mode` | Shell ENTRYPOINT or args overridden/misplaced | Use exec ENTRYPOINT + exec CMD, check `docker inspect` |
| `docker stop` stalls until `SIGKILL` | Shell holds PID 1 without forwarding `SIGTERM`, or slow shutdown | Use exec ENTRYPOINT, check graceful timeout and logs |
| Java is PID 2 despite exec ENTRYPOINT | `--init` or supervisor active | Inspect process tree; may be intentional |
| `JAVA_OPTS=-Xmx256m` has no effect | JVM does not read `JAVA_OPTS` natively | Use `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` |
| `NOTE: Picked up JDK_JAVA_OPTIONS` on stderr | Java launcher notice for env options | Normal; verify flags rather than treating as crash |
| `JDK_JAVA_OPTIONS=-jar ...` aborts launcher | Variable holds disallowed launcher option | Keep only supported VM/launcher flags; leave `-jar` in ENTRYPOINT |
| `java -jar` cannot find file | Wrong `COPY` artifact name, `.dockerignore` excluded JAR | Build Maven first, inspect image path |
| Container running yet host cannot connect | Missing `-p`, wrong internal port, or app not ready | `docker run -p HOST:CONTAINER`, check logs/port |
| App listens on 9090 while Docker maps 8080 | `--server.port` overrode `CMD` without updating mapping | Use `-p 18081:9090` to match |
| JVM OOM-killed despite `-Xmx` below limit | Native memory + heap exceeded container limit | Check cgroups, metaspace, stacks, GC, and headroom |
| JDK option accidentally applied to Maven during image build | JVM env variable exported too broadly | Scope env to runtime process/stage only |
| `entrypoint.sh` reports `not found` despite existing | CRLF line endings, wrong shebang, not executable | Convert to LF, `chmod +x`, check `#!/bin/sh` |
| `"$@"` missing in script | App args from `CMD`/run not forwarded | Use `exec java ... -jar ... "$@"` |
| `docker run IMAGE --entrypoint ...` fails | `--entrypoint` is a **Docker option**, must precede IMAGE | `docker run --entrypoint java IMAGE -Xmx... -jar ...` |
| Testing JVM flags on image without JDK tools | JRE image lacks `jcmd` | Use JVM observability or a JDK diagnostic image |
| Debug endpoint leaks secrets | Returned full JVM args/env over HTTP | Expose only dummy non-sensitive info; remove probe in prod |

## 17. Pre-Release Verification Gates

### Gate A — Image Entrypoint

- [ ] `docker image inspect` confirms `Entrypoint` is an array, not a shell-form string.
- [ ] Flags are separate tokens and any hardcoded JVM options sit **before `-jar`** in `ENTRYPOINT`.
- [ ] `CMD` contains only default application arguments or intended defaults.
- [ ] No literal `$JAVA_OPTS` inside the exec argument array.

### Gate B — Java/Spring Config

- [ ] Java 17 runtime is valid; executable JAR includes Boot loader and runtime dependencies.
- [ ] Starting with `docker run -p ...` succeeds and `/probe` returns HTTP 200.
- [ ] `-e JDK_JAVA_OPTIONS='-Ddemo.jvm.tag=from-env'` updates `jvmTag` on the endpoint.
- [ ] `--app.mode=blue` after the image updates `appMode` as expected.
- [ ] `-Xmx` configuration verified via JVM metrics/diagnostics, not guessed from `docker inspect`.

### Gate C — Shutdown and Operations

- [ ] `docker stop` delivers the stop signal cleanly and the app completes or logs issues within the grace period.
- [ ] Spring graceful shutdown configured if the service must drain in-flight requests.
- [ ] Container runs non-root unless strictly required, with proper filesystem permissions.
- [ ] Memory limit leaves headroom beyond heap; no secrets in args or logs.
- [ ] Logs, health/readiness probes, and rollback strategy defined.

### Gate D — Reproducibility and Deployment

- [ ] Image tag/digest and app JAR version pinned/recorded.
- [ ] Dependencies and base images sourced from trusted registries.
- [ ] Application and JVM configs managed as deployment inputs, with no secrets baked into the image.
- [ ] Compose/Kubernetes manifests do not accidentally alter `ENTRYPOINT` or place JVM flags after `-jar`.
- [ ] Startup success is never equated with proper signal handling or memory sizing.

## 18. Self-Check Questions with Answers

**1. Why prefer `ENTRYPOINT ["java","-jar","/app/app.jar"]`?**

Because Docker invokes Java directly, cleanly separates arguments, appends `CMD`/runtime args, and avoids a parent shell failing to forward `SIGTERM`. It is a strong default for single-process Spring Boot apps.

**2. With that exec `ENTRYPOINT`, does `docker run image -Xmx256m` set the JVM heap?**

No. Docker appends `-Xmx256m` **after the JAR file**, so the Java launcher passes it as an application argument.

**3. How do you change `-Xmx` at runtime without editing the Dockerfile?**

Use `JDK_JAVA_OPTIONS` or `JAVA_TOOL_OPTIONS` as supported by Java 17 and verified in testing. For specialized images/launchers, consult their documentation.

**4. Is `JAVA_OPTS` the same as `JAVA_TOOL_OPTIONS`?**

No. `JAVA_OPTS` is merely a script/buildpack convention, whereas `JAVA_TOOL_OPTIONS` is natively supported by the JVM. With an exec `ENTRYPOINT` calling Java directly, `JAVA_OPTS` has no automatic effect.

**5. Where does `CMD ["--server.port=8080"]` go at runtime?**

It appends after `/app/app.jar` as a Spring Boot application argument unless overridden by `docker run IMAGE ...`.

**6. Why can shell-form `ENTRYPOINT java -jar app.jar` prevent `docker stop` from shutting down gracefully?**

The shell typically holds PID 1 and fails to forward `SIGTERM` cleanly to the child Java process. Use exec form, or `exec` inside a script when a wrapper is needed.

**7. When using `--init`, is Java still PID 1?**

Not necessarily. The init process typically holds PID 1 to forward signals and reap children; Java runs as a managed child process.

**8. Should `-Dsecret.password=...` go in `JDK_JAVA_OPTIONS`?**

Not recommended. JVM flags and container env vars can leak through multiple operational channels. Use your environment's secure secret mechanism.

**9. What happens if `--server.port=9090` is passed after the image while still mapping `-p 18081:8080`?**

The app listens on 9090 inside the container while Docker forwards to 8080, causing a port mismatch. Update the mapping to `-p 18081:9090`.

**10. When `docker stop` runs, is `APP_CONTEXT_CLOSED` guaranteed to appear?**

No. It prints only when the Spring context closes and `@PreDestroy` completes; `SIGKILL` or timeouts can prevent it.

**11. Is `ENTRYPOINT ["java", "$JDK_JAVA_OPTIONS", "-jar", "/app/app.jar"]` valid?**

No. Docker does not expand that string argument. Let the Java launcher read `JDK_JAVA_OPTIONS` from the environment natively; do not place it as a literal JSON token.

**12. Why shouldn't `-Xmx` equal the container's entire memory limit?**

Heap is only part of a Java process's memory footprint; leave room for native allocations, metaspace, threads, code cache, and GC structures.

## 19. Summary and Design Decisions

- **Default to exec ENTRYPOINT:** `["java","-jar","/app/app.jar"]`.
- **App defaults:** place in `CMD` or Spring environment/config.
- **Fixed JVM flags:** place before `-jar` inside exec `ENTRYPOINT`.
- **Per-environment JVM flags:** use `JDK_JAVA_OPTIONS` (or `JAVA_TOOL_OPTIONS` where appropriate); never put `-Xmx` in `CMD` after the JAR.
- **Dynamic pre-launch setup:** use a short script ending in `exec java ... "$@"`, never `eval`.
- **Verify stop signals:** test `docker stop` and check Spring shutdown logs, aligning the grace period.
- **Verify operations:** proper port mappings, memory headroom, non-root permissions, secrets, and deployment overrides.

**Conclusion:** For Spring Boot in Docker, choosing **exec-form `ENTRYPOINT`** keeps Java process semantics clean and makes stop signals far more reliable. `JDK_JAVA_OPTIONS`/`JAVA_TOOL_OPTIONS` pass runtime JVM options **without breaking exec form**, while `CMD` and trailing image arguments carry **application arguments**. Always verify `System.getProperty`, Spring `Environment`, JVM memory, and `docker stop` against the real image rather than only reading the Dockerfile.

## 20. Official Documentation

1. [Docker Docs — Dockerfile reference: Shell and exec form, ENTRYPOINT, CMD](https://docs.docker.com/reference/dockerfile/)
2. [Docker Docs — Build check JSONArgsRecommended](https://docs.docker.com/reference/build-checks/json-args-recommended/)
3. [Docker Docs — docker container run: --init, --memory, port mapping, environment](https://docs.docker.com/reference/cli/docker/container/run/)
4. [Docker Docs — docker container stop: SIGTERM and grace period](https://docs.docker.com/reference/cli/docker/container/stop/)
5. [Oracle Java 17 — The java Command and JDK_JAVA_OPTIONS](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
6. [Oracle Java 17 — JVM TI / JAVA_TOOL_OPTIONS](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
7. [Spring Boot — Dockerfiles and Executable JARs](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
8. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
9. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
10. [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)