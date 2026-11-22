# Console in Containers — Java Logging via stdout/stderr with Docker and Kubernetes

## 1. What is console logging in containers?

**Console logging in containers** is the practice where an application writes log events to **standard output (stdout)** or **standard error (stderr)** of the process running inside a container, so that **the container runtime and observability infrastructure** can collect, display, forward, and store them.

Instead of requiring the application to create its own files such as `/var/log/orders/application.log` inside the container's filesystem, the application can write:

~~~text
INFO | event=service.started service=orders port=8080
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

The three lines above are an **illustrative format**, not the default format of every Java library. When using Logback, the **ConsoleAppender** and encoder configuration determine the content, which levels are printed, and the target stream.

**Key principle:** Writing logs to stdout/stderr is the **application's** responsibility; reading the streams and providing commands such as `docker logs` or `kubectl logs` is the **container runtime/orchestrator's** responsibility; centralized storage, long-term search, access control, and retention are the responsibility of the **logging platform** when deployed.

Calling `LOG.info(...)` in the application does not guarantee that the log line has been collected and durably stored. It may be filtered at the logger/appender, not flushed, lost when the container stops, or fall outside the runtime's storage policy.

### Learning Objectives

After this lesson, you will be able to explain:

1. Where stdout and stderr sit in the application → runtime → collector chain.
2. How Docker and Kubernetes treat console logs differently from log files inside a container.
3. How to configure Logback `ConsoleAppender` to write Java logs to the right stream.
4. Why you should not arbitrarily use `System.out.println` instead of a logging framework.
5. How to view logs with `docker logs` and `kubectl logs`, as well as the limitations of those commands.
6. How to control levels, format, JSON Lines, exceptions, MDC, log volume, and security.
7. Common issues when logs disappear, duplicate, go to the wrong stream, or get truncated.

## 2. The Path of a Log Record in a Container

A simplified pipeline:

~~~text
Java application
  |
  |  LOG.info(...), LOG.warn(...), LOG.error(...)
  v
SLF4J API / Logger (Logback or another backend)
  |
  |  effective level + filter
  v
ConsoleAppender + Encoder
  |
  +-------------------------+
  |                         |
  v                         v
stdout (FD 1)           stderr (FD 2)
  |                         |
  +-------------+-----------+
                |
                v
        Container runtime
                |
                v
      Node-level logging files
        / logging driver
                |
          +-----+------+
          |            |
          v            v
    docker logs    kubelet/kubectl logs
          |
          v
    Optional log collector/agent
          |
          v
  Central log storage / search / alerts
~~~

This diagram is **conceptual**: Docker collects logs via a **logging driver**, while Kubernetes interacts with the container runtime through the appropriate interface and kubelet manages log access. Not every environment has all the components shown in the diagram or stores files the same way.

The path can include multiple filtering layers:

- **Application logger:** `LOG.debug(...)` may be dropped when the root level is `INFO`.
- **Appender/Handler:** receives the event but may still reject it via a filter or write it to a different stream.
- **Runtime:** has its own driver mechanism, format, rotation, and local storage.
- **Collector:** may parse, enrich metadata, sample, enforce size limits, or fail to forward.
- **Log store:** has its own retention, access control, indexing, and cost characteristics.

Therefore, **not seeing a log in a dashboard is not enough to conclude that the Java code branch did not execute**.

## 3. stdout, stderr, and the Meaning of the Two Streams

The two standard streams are process I/O channels:

| Stream | Unix File Descriptor | Typical Usage |
| --- | --- | --- |
| stdin | 0 | Receiving input |
| stdout | 1 | Primary output or application logs, depending on policy |
| stderr | 2 | Diagnostic information, warnings/errors, depending on policy |

**There is no JVM rule stating that every ERROR must print to stderr and every INFO must print to stdout.** Logging frameworks choose the target based on configuration. For example:

- **Logback ConsoleAppender** typically writes to **System.out** by default; the target can be set to `System.err`.
- **java.util.logging.ConsoleHandler** (JUL) writes to **System.err** by default.
- **System.out.println(...)** and **System.err.println(...)** print directly to their respective streams without logger level logic.
- **Log4j 2 ConsoleAppender** has its own configuration and API; Logback configuration cannot be used as-is to control it.

In many container systems, both stdout and stderr are collected, but **stream is not log level**. An `ERROR` line can appear on stdout if the appender is configured that way. Level classification in a collector should rely on a trustworthy **level** field rather than mechanically assuming `stream=stderr` means a critical error.

### When should you use stdout, and when stderr?

For **long-running web/container services**, using a single consistent stream (usually stdout) with a level field is often simpler to collect. For **CLI tools** that need to return JSON or CSV on stdout to another program, consider sending diagnostic logs to stderr so you do not corrupt machine-readable output.

If both streams are used in parallel, the collector may receive them in a different order than Java emitted the events. **Do not treat line order across merged stdout/stderr as a strict global order**; use timestamps, `requestId`, and `traceId` for analysis.

## 4. How Does Docker Handle Console Logs?

When a container runs, Docker can capture stdout/stderr data through the configured **logging driver**. Some drivers use local storage mechanisms; others forward logs to external systems. The default driver and specific options **depend on the Docker daemon configuration and how the container is run**; do not assume every machine uses the same driver.

**docker logs** is the command commonly used to view logs that the Docker runtime makes available for a container. It is **not** a command for reading arbitrary files inside the container and **does not replace** a long-term centralized logging platform.

Some practice commands:

~~~bash
docker run --name order-console-demo java-console-demo:1
docker logs order-console-demo
docker logs --timestamps order-console-demo
docker logs --tail 20 order-console-demo
docker rm order-console-demo
~~~

This example assumes the **java-console-demo:1** image has already been built in Section 7 and no container with a conflicting name exists. In the example, the Java application finishes quickly; `docker run` displays the logs as it runs, and `docker logs` can later re-read the lines stored by the driver. Do not run with **--rm** if you want to inspect the exited container later with `docker logs`, because Docker removes the container object after it exits.

For long-running containers, you can stream logs in real time:

~~~bash
docker logs --follow --tail 100 order-console-demo
~~~

If the container has already exited, `--follow` does not restart the application; it only reads the logs that remain accessible. Whether logs can be re-read depends on the driver, configuration, and container lifecycle.

### Logging driver and rotation

Docker allows choosing a logging driver and options. Here is an example configuration when creating a container using the `json-file` driver with per-file limits:

~~~bash
docker run --name order-console-rotated \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  java-console-demo:1
~~~

In this example, **10m** and **3** are illustrative configuration values, **not mandatory defaults**. Rotation options vary by driver; do not copy `max-size`/`max-file` to every driver without checking the corresponding driver documentation.

**Do not directly edit the Docker daemon's internal log files** to free up disk space while a container is running; use the management and rotation mechanisms of the runtime and logging platform.

To inspect the logging driver selected on the daemon or container, use the appropriate inspection commands, for example:

~~~bash
docker info --format '{{.LoggingDriver}}'
docker inspect --format '{{.HostConfig.LogConfig.Type}}' order-console-demo
~~~

The `inspect` command requires the `order-console-demo` container to still exist. The daemon's default driver does not necessarily match the driver configured specifically for an individual container.

### Using the console instead of writing files inside the image

A file in the container's filesystem may **not appear in `docker logs`** if the application only writes to that file and nothing forwards the file to stdout/stderr. The file can also disappear when the container is removed unless it is placed on a persistent volume or an external storage system.

For typical containerized deployments, the easiest approach to operate is for **the application to log to the console**, letting the runtime/collector manage log ingestion and storage. Not every application is forbidden from writing files; some audit requirements or legacy software still need files, volumes, or collection sidecars, but those must be designed explicitly.

## 5. How Does Kubernetes Read Container Logs?

In Kubernetes, the kubelet and container runtime participate in managing container logs on each node. The **kubectl logs** command asks Kubernetes to return the log contents of a container belonging to a Pod.

Suppose there is a Pod **order-console-demo** in namespace **demo**, with a container named **app**:

~~~bash
kubectl logs -n demo pod/order-console-demo -c app
kubectl logs -n demo pod/order-console-demo -c app --timestamps
kubectl logs -n demo pod/order-console-demo -c app --since=10m
kubectl logs -n demo pod/order-console-demo -c app --follow
~~~

These are **illustrative commands with specific resource names**; the Pod, namespace, and container must actually exist for the commands to work. The container name **app** is useful when a Pod has multiple containers. If a Pod has only a single container, you can usually omit the `-c` flag.

Scenarios to distinguish:

- **Multi-container Pods:** each container's logs are accessed separately, so you must specify the right container name.
- **Restarted containers:** you can use **--previous** to view logs from the previous container instance **if those logs are still available** in that Pod's context.
- **Deleted Pods or rotated/expired node logs:** `kubectl logs` is not guaranteed to retrieve all historical logs.
- **Streaming with `--follow`:** only follows the accessible stream; it does not guarantee that data has been durably written to a log store.

Example of viewing the previous run of a container in a Pod:

~~~bash
kubectl logs -n demo pod/order-console-demo -c app --previous
~~~

If there is no previously terminated container or the logs are no longer available, the command will report that no suitable content was found. Do not treat the existence of `kubectl logs` as proof that the cluster has centralized logging.

### Node-level and cluster-level logging

The kubelet can manage container log file rotation on the node according to its configuration. **kubectl logs is a tool for retrieving logs per container/Pod**, not a cluster-wide search solution with long-term retention.

Systems that need long-term querying or multi-node aggregation usually include a **log agent/collector** that forwards events from the node/runtime to a storage and search service. Operating the collector, storage policies, access control, JSON parsing, and alerting is separate from the application calling `Logger`.

**Practical note:** logs written to the node by the runtime but not yet read by the collector, logs truncated due to size, or a failing collector can all cause missing data in centralized queries.

## 6. Java Logging in Containers: Choosing the Right API

A Java application can use:

| Option | Mechanism | Writing to Console |
| --- | --- | --- |
| **SLF4J + Logback** | Code calls SLF4J, Logback backend processes | `ConsoleAppender` targeting `System.out`/`System.err` |
| **JUL** | Built-in JDK API | `ConsoleHandler` defaults to stderr; custom handlers can write to stdout |
| **Log4j 2** | Log4j 2 API/backend | Log4j 2 `ConsoleAppender`, configured via Log4j 2 itself |
| **System.out.println** | Writes String directly | stdout, no automatic levels/filters/logging schema |

For new projects or projects standardized on SLF4J, **using a logger and `ConsoleAppender`** is generally much easier to maintain than scattering `println` calls throughout the code. Benefits include:

- Per-package/module and per-environment log levels.
- Consistent pattern or structured encoder.
- Throwable/stack trace handling through the backend.
- MDC and request/trace ID correlation when properly configured.
- Changing destinations and verbosity without modifying every log call.
- Filters to reduce cost and avoid outputting unnecessary sensitive information.

In containers, an easy rule of thumb is: **business code calls Logger, backend configuration routes logs to the console, and infrastructure ingests the stream**.


## 7. Java 17 + Maven + Docker Example: Logging to stdout

This example creates a Java program that **runs on a machine with Maven/JDK 17**, then packages it into a Docker image. The application uses **org.slf4j.Logger** with **Logback Classic**, root level at `INFO`, and a `ConsoleAppender` writing to `System.out`.

To keep output deterministic, the demo formatter intentionally **does not print timestamps**; in production, you must add a standard timestamp or rely on runtime/collector metadata defined by your organization.

### 7.1. Project Structure

~~~text
java-console-demo/
├── pom.xml
├── Dockerfile
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ContainerConsoleDemo.java
        └── resources/
            └── logback.xml
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>java-console-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.7.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The pinned versions in this example are solely for reproducing the lesson, **not a claim that they are the latest or safest versions currently available**. Real projects should follow dependency management practices, check compatibility and security patches, and avoid putting multiple SLF4J providers on the runtime classpath.

### 7.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Logback picks up **logback.xml on the classpath** if not overridden by another framework or configuration:

- **Root INFO:** `DEBUG` is not emitted; `INFO`, `WARN`, and `ERROR` are evaluated for output.
- **ConsoleAppender:** writes to **System.out**.
- **Pattern:** prints only the log level and message, without timestamps or variable fields, so the demo produces fixed stdout.
- **UTF-8:** supports Unicode when the consumer decodes it accordingly.
- **Appender attached only at root:** avoids duplicating events in the example.

**%level | %msg%n** is Logback pattern syntax; **{}** in the Java calls is an SLF4J placeholder, not the same formatting mechanism.

### 7.4. src/main/java/demo/ContainerConsoleDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ContainerConsoleDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ContainerConsoleDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=service.debug enabled=false");

        LOG.info("event=service.started service={} port={}",
                "orders", 8080);

        LOG.warn("event=dependency.slow dependency={} durationMs={}",
                "catalog", 750);

        LOG.error("event=request.failed requestId={} errorCode={}",
                "req-42", "UPSTREAM_TIMEOUT");
    }
}
~~~

This is a **complete Java class**. Fixed values make the output verifiable. It does not start an HTTP server or run indefinitely; the process exits after logging so the Docker exercise stays simple.

### 7.5. Compiling and Running Locally

You need **JDK 17+**, Maven, and downloadable dependencies (or dependencies already present in your Maven cache). Inside the **java-console-demo** directory, run:

~~~bash
mvn -q -DskipTests package dependency:copy-dependencies
java -cp "target/classes:target/dependency/*" demo.ContainerConsoleDemo
~~~

The `java` command above uses **:** as the classpath separator for Linux/macOS. In **Windows PowerShell**, use **;**:

~~~powershell
java -cp "target/classes;target/dependency/*" demo.ContainerConsoleDemo
~~~

**Stdout emitted by the Java program** when using the `logback.xml` above:

~~~text
INFO | event=service.started service=orders port=8080
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

**No log lines are expected on stderr from the application.** The `DEBUG` call is filtered out by root `INFO`; the program does not print anything else with `println`. Any build, configuration, or runtime error messages, if they occur, are outside the three expected business log lines.

### 7.6. Multi-stage Dockerfile

Create **Dockerfile**:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package dependency:copy-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/target/classes /app/classes
COPY --from=build /src/target/dependency /app/lib
ENTRYPOINT ["java", "-cp", "/app/classes:/app/lib/*", "demo.ContainerConsoleDemo"]
~~~

Explanation:

1. The **build** stage uses Maven + JDK 17 to compile and copy runtime dependencies into `target/dependency`.
2. The runtime stage uses **Java 17 JRE**, avoiding the need to include Maven in the runtime image.
3. **target/classes** contains the compiled classes and the **logback.xml** resource.
4. **target/dependency** contains the library JARs required for SLF4J/Logback; the classpath **/app/lib/* ** is expanded by Java on Linux containers.
5. **Exec-array ENTRYPOINT** runs `java` directly as the main process instead of wrapping it in a shell script that fails to forward signals.
6. The Java process's stdout/stderr go to the streams managed by the container runtime.

The image names and tags here are practice examples. For real deployments, pin base-image digests or follow your organization's verified image policy, apply CVE updates, and run as a non-privileged user where appropriate.

### 7.7. Building the Image and Viewing Logs

From the directory containing the `Dockerfile`:

~~~bash
docker build -t java-console-demo:1 .
docker run --name order-console-demo java-console-demo:1
docker logs order-console-demo
docker logs --timestamps order-console-demo
docker rm order-console-demo
~~~

**The application log content in `docker run`/`docker logs`** is the three `INFO`, `WARN`, `ERROR` lines shown in Section 7.5. If you pass **--timestamps**, Docker may prepend runtime timestamps when displaying them; thus the full output of `docker logs --timestamps` **will not be identical character-for-character to the three demo lines**, though the message portion from Java remains the same.

Note that the application exits immediately. Do not use **docker run --rm** in this same command sequence if you want to inspect `docker logs` afterward; `--rm` deletes the container when it exits.

### 7.8. Disabling INFO Without Changing Code

Change `logback.xml`:

~~~xml
<root level="WARN">
    <appender-ref ref="STDOUT"/>
</root>
~~~

Rebuild the image and run with a new container name, or remove the old container before reusing its name. Now Java's stdout logs only contain:

~~~text
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

This demonstrates that **levels and appenders are configured in the backend**; Docker only receives the lines that the application actually writes to the stream. The runtime cannot recover a `DEBUG`/`INFO` event that the application filtered out before output.

## 8. Routing INFO/WARN to stdout and ERROR to stderr

Some platforms want to keep errors on a separate stream from normal logs. With Logback, **each `ConsoleAppender` has only one target**, so you can define two appenders with appropriate filters.

Example **alternative `logback.xml`** (do not use at the same time as the Section 7 example file):

~~~xml
<configuration>
    <appender name="OUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="OUT"/>
        <appender-ref ref="ERR"/>
    </root>
</configuration>
~~~

In the standard Logback level scale:

- **OUT** writes `INFO` and `WARN`, denying `ERROR` via `LevelFilter`.
- **ERR** writes only `ERROR` via `ThresholdFilter`.
- **Root INFO** does not emit `DEBUG` from loggers inheriting `INFO`.
- `ERROR` is not written to both streams simultaneously as would happen if neither appender had a filter.

This **does not mean `ERROR` is "a special stderr data type"**. It is simply a backend routing decision.

To observe stream separation in bash, you can run after the Maven build:

~~~bash
java -cp "target/classes:target/dependency/*" \
  demo.ContainerConsoleDemo > out.log 2> err.log
~~~

With the alternative configuration above, **out.log** contains `INFO` and `WARN`; **err.log** contains `ERROR`. When an external tool merges the two streams, their combined order may differ from the emission order.

When using Kubernetes or Docker, check how your collector handles stdout/stderr before deciding to split streams; many infrastructures prefer keeping all logs on a single stream with an explicit `level` field.

## 9. Structured Logging and One Log Event per Line

In containers, log collection tools typically process data **line by line**. Therefore, for multi-service systems, a **JSON Lines** format (each event as a JSON object on a single physical line) can be more convenient than free-form text.

Example JSON logs:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"orders","event":"order.created","requestId":"req-42","durationMs":18}
{"timestamp":"2026-11-09T10:15:02.100Z","level":"ERROR","service":"orders","event":"payment.failed","requestId":"req-42","errorCode":"UPSTREAM_TIMEOUT"}
~~~

This is **illustrative data**, not the output of the Section 7 application. It offers several benefits:

- **Stable field names:** `service`, `event`, `requestId`, `errorCode`.
- **Clear data types:** `durationMs` is numeric so comparisons work when the collector parses it properly.
- **Timezone-aware timestamps:** the `Z` suffix represents UTC.
- **Easy filtering by `requestId`:** view events belonging to the same request or trace.
- **Fewer line-splitting errors:** a proper JSON serializer escapes newlines inside values.

However, **merely printing a string that looks like JSON to stdout does not mean the collector will automatically parse and index its fields**. You need a real JSON encoder in the backend, a clear schema, and matching log collector/ingestion configuration.

### Exceptions and multi-line stack traces

When Java logs a `Throwable`, a text encoder may print **multiple lines**:

~~~text
ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
java.io.IOException: dependency unavailable
    at demo.PaymentClient.call(PaymentClient.java:42)
    at demo.OrderService.pay(OrderService.java:81)
~~~

This is an **illustrative sample**, not a stack trace from the Section 7 program. If a collector relies solely on newlines, it may treat each line of the stack trace as a separate event and break queries.

Common solutions:

1. **Collector multiline parser**: recognizes the start of an event and groups subsequent exception lines according to rules.
2. **Structured exception fields**: outputs exception type/message/stack trace into JSON fields, escaping newlines inside values.
3. **Clear schema design**: one event carries an error code and context, avoiding repeating the same stack trace at every layer.

Do not strip `Throwable`s just to keep logs single-line. Choose a representation supported by both your Java backend and your collector.

### Escaping and log injection

Messages originating from requests may contain quotes, backslashes, newlines, or control characters. If concatenated directly into text or hand-rolled JSON, users can accidentally or intentionally forge fake log lines.

Use a serializer/encoder that handles escaping properly and **do not unnecessarily log raw untrusted data**. For sensitive data, escaping is not enough: you also need masking, data minimization, and access control.

## 10. Timestamps: Java's or the Runtime's?

A log line can have multiple timestamps:

- **Event timestamp:** the time when Java/the logging framework recorded the event.
- **Runtime timestamp:** the time when the container runtime wrote/stamped the record.
- **Ingestion timestamp:** the time when the log collector/storage received the data.

These timestamps can differ due to buffering, networking, queuing, or clock skew. When using **docker logs --timestamps** or **kubectl logs --timestamps**, the commands may display timestamps from the runtime/cluster logging mechanism, **not timestamps automatically inserted into the message by the Java logger**.

For production observability, agree on:

1. Which timestamp is called **timestamp** in the log schema.
2. Whether an explicit timezone (usually UTC) is required.
3. Precision, such as milliseconds or microseconds.
4. How to distinguish event time from collector receive time.
5. How machine clocks and drift across nodes are controlled.

**Do not omit timestamps from production logs just because a learning example drops them for deterministic stdout.** In demos or tests, you can inject a fixed clock or parse the time field separately when comparing against a schema.

## 11. Process Lifecycle: PID 1, Signals, and Flushing

A container usually has one main process; when that process exits, the container stops. This affects logging reliability.

### Exec-array ENTRYPOINT

The Dockerfile in Section 7 uses:

~~~dockerfile
ENTRYPOINT ["java", "-cp", "/app/classes:/app/lib/*", "demo.ContainerConsoleDemo"]
~~~

This is the **exec form**, which does not wrap Java in an unnecessary shell command. For a long-running service, this configuration delivers signals from the container runtime to the Java process more cleanly than many shell wrappers that do not use `exec`.

When Docker or Kubernetes requests a stop, the process may receive termination signals according to runtime policy. Applications should implement **graceful shutdown**: stop accepting new work, finish or cancel in-flight tasks appropriately, close resources, and let the logging backend flush/stop according to its lifecycle.

**Do not assume every signal or forced kill is handled completely.** If a container is killed abruptly, a node dies, or shutdown times out, events sitting in buffers/async queues may never be written to the stream. Even when the logger flushes locally, a remote collector may not have durably stored them yet.

### AsyncAppender and console I/O cost

Logback provides **AsyncAppender** to offload some I/O work to a worker thread via a queue:

~~~text
Application thread
       |
       v
  AsyncAppender -> queue -> ConsoleAppender -> stdout
~~~

This can reduce the time business threads spend waiting on console writes under heavy load. However, the queue is bounded and has a discard or block policy when full; abrupt shutdowns can also lose queued events that have not yet been dispatched.

Measure **log volume, message size, queue capacity, discard/block policy, and shutdown flush** under realistic load. Do not assume switching to async is always faster or safer.

### stdout buffering

Some programs write to stdout through a buffer, so the time a log appears can differ from when the method was called. Java backends may also have their own flush policies. For instance, JUL `StreamHandler` may need **flush()** in very short-lived programs; Logback `ConsoleAppender` has its own writing mechanism.

Do not conclude that an unprinted line means `Logger` never ran. Check levels/filters, buffering, the runtime, the reader, the collector, and when the process exited.

## 12. Are Log Files in Containers Always Wrong?

No. You just need to understand the different responsibilities.

| Approach | Appropriate When | What to Watch Out For |
| --- | --- | --- |
| **ConsoleAppender → stdout/stderr** | Containerized services where infrastructure collects log streams | Driver/collector, rotation, retention, sensitive data |
| **FileAppender inside container** | Legacy apps or special internal file requirements | Files may not appear in `docker logs`; filesystem is lost when container is removed |
| **File on persistent volume** | Specific file retention policies | Volume management, multiple replicas, rotation, permissions, and collection |
| **Sidecar/agent reading files** | Systems that need to parse/ship file logs | Shared paths, multi-container policies, extra resource overhead |
| **Dedicated audit/event store** | Events requiring durable business-contract guarantees | Do not rely on console logs, which can be lost |

The key distinction is between **logging for observability** and **storing business events with durability guarantees**. A `LOG.info` call does not replace a database transaction commit, the outbox pattern, or a compliance audit store.

When running multiple replicas, a file path inside a container is not a single place holding all logs for the service. Console logging + a centralized collector generally avoids having to inspect individual nodes or volumes to troubleshoot incidents.

## 13. Container Log Security

Console logs may be collected by daemons, container runtimes, node agents, cloud services, CI/CD systems, or analytics platforms. Do not treat them as data "only printed temporarily in a developer's terminal".

Principles:

- **Never log passwords, API keys, bearer tokens, refresh tokens, session cookies, private keys, or cardholder data** at any level.
- Do not log **entire HTTP bodies, `Authorization` headers, or `toString()` of objects** containing private data by default.
- Exceptions and stack traces can expose internal details, paths, or sensitive payloads; apply masking and access control.
- Request IDs or business identifiers can also be sensitive depending on policy. Avoid using IDs containing personal data directly when unnecessary.
- Use encoders that escape untrusted values to mitigate log forging.
- Restrict log-reading permissions on the Docker daemon, cluster, and centralized platform; permission to view a Pod should not automatically grant permission to read all log contents.
- Enforce **retention, deletion, and size-limit** policies; long-lived logs can turn into an unintended repository of sensitive data.
- If adding **traceId, requestId** for troubleshooting, ensure they are validly generated and propagated across services without embedding secrets in the IDs.

`DEBUG`/`TRACE` levels can expose far more detail when enabled in production, so enable them selectively and with a time limit. Never log secrets at `DEBUG` with the excuse that "production normally runs at INFO".

## 14. Performance, Log Volume, and Observability Systems

Console logging has costs at multiple layers: formatting messages, encoding JSON/text, writing to the stream, runtime storage/packaging, collector reading/forwarding, and log store storage/indexing.

Ways to keep it under control:

1. Set **appropriate levels**: `INFO` for important events, `WARN` for anomalies, `ERROR` for failures, `DEBUG`/`TRACE` for targeted investigation.
2. Avoid logging an `INFO` line for every item inside high-throughput loops without diagnostic value.
3. Use **parameterized logging** to reduce unnecessary string concatenation.
4. Avoid evaluating CPU-intensive expressions before the `Logger` checks the level; use guards or supported lazy mechanisms.
5. Use **metrics** for counts/rates/latencies over time, and **tracing** for cross-service requests.
6. Control stack trace sizes and attached payloads without mechanically stripping critical evidence.
7. Check runtime rotation/storage and collector quotas/retention.
8. Monitor **dropped logs, parse errors, queue lag, and disk usage** when your infrastructure exposes those metrics.

SLF4J example:

~~~java
// Illustrative snippet requiring LOG, payload, and expensiveSerialize().
LOG.debug("payload={}", expensiveSerialize(payload));

if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

The first call still evaluates **expensiveSerialize(payload)** when `DEBUG` is disabled because Java evaluates method arguments before the call. The `if` guard in the second call avoids that cost when the level is off. **isDebugEnabled does not guarantee that the appender/collector will successfully record the event**.

Never place business logic with required side effects inside a block meant only for logging optimization.

## 15. Common Pitfalls

| Issue | Symptom | Resolution |
| --- | --- | --- |
| Logs written only to a file inside the container | Nothing in `docker logs`/`kubectl logs` | Use console logging or a dedicated file-reading agent |
| Using JUL `ConsoleHandler` expecting stdout | Redirected the wrong stream | Remember JUL defaults to stderr; Logback `ConsoleAppender` usually defaults to stdout |
| Root `INFO` while looking for `DEBUG` | No debug lines appear | Adjust the effective level of the right logger |
| Appender filter blocks events | Code logs, but nothing shows up | Check filters, `appender-ref`, and `additivity` |
| Attaching appender to both child logger and root | Same event appears twice | Review `appender-ref` and `additivity` |
| Only SLF4J API added, missing provider | Logs not handled as expected | Add a single compatible SLF4J provider |
| Multiple conflicting providers/bridges | Unexpected logging backend behavior | Inspect dependency tree and routing |
| Using `docker run --rm` then `docker logs` | Container already deleted | Run without `--rm` if you need to inspect logs later |
| Checking the wrong Pod/container in Kubernetes | Logs appear missing | Specify the correct namespace, pod, and `-c` container |
| Expecting `kubectl logs` to keep infinite history | Older logs are gone | Use a collector and appropriate retention |
| No runtime log rotation configured | Node/host disk usage grows | Configure driver/kubelet rotation policies for your infrastructure |
| Messages with raw newlines/stack traces | One event splits into many lines | Use JSON Lines or a multiline parser |
| Timestamps without timezone | Hard to compare across nodes | Standardize on timestamps with offset/UTC |
| Leaving system-wide `DEBUG` on long-term | Log volume and cost spike | Enable per logger with a time limit |
| Missing flush or abrupt termination | Final logs lost before shutdown | Implement graceful shutdown and flush policy |
| Writing tokens/raw requests to stdout | Collector stores sensitive data | Data minimization, masking, access control |
| Treating `stream=stderr` as `severity=ERROR` | Logs misclassified | Read the `level` field or normalize in the collector |

## 16. Troubleshooting Checklist When Container Logs Are Missing

When you suspect logs are missing, check in order:

1. **Did Java actually call the Logger?** Was the event triggered in the scenario being tested?
2. **Logger level and filters:** did the event pass the logger threshold, appender filters, and `TurboFilter`?
3. **Which backend is active:** Logback/JUL/Log4j 2; are the right config file and provider loaded?
4. **Appender/Handler:** is the target `System.out`, `System.err`, or a file?
5. **Docker:** does the container still exist, which logging driver is active, and what rotation/caching is configured?
6. **Kubernetes:** right namespace, Pod, container name, current vs. `--previous` container?
7. **Did data reach the stream:** any buffering/flushing, shutdown lifecycle, or PID 1 signal-forwarding issues?
8. **Collector:** is it running, and is it misparsing JSON/multiline logs or filtering by stream?
9. **Retention:** did the data expire, get rotated/truncated, or was the container/Pod deleted?
10. **Correlation:** right `requestId`/`traceId`/time range? Is the timestamp from the app or the runtime?
11. **Throughput:** is the queue/appender/collector congested or dropping events under load?
12. **Security:** are logs being redacted, or do you lack query permissions?

Do not blindly change loggers en masse to `INFO`/`ERROR` "just to make sure it prints" without knowing which layer dropped the log. Raising levels indiscriminately can flood logs, increase costs, and risk exposing data.

## 17. Self-Check Questions

**Question 1.** By default, does Logback `ConsoleAppender` target stdout or stderr?

**Answer:** Usually **System.out**; the target can be set to `System.err`. By contrast, JUL `ConsoleHandler` defaults to stderr.

**Question 2.** Why might `/app/logs/app.log` have content while `docker logs` is empty?

**Answer:** `docker logs` reads logs via the logging driver from stdout/stderr; it does not automatically read arbitrary files in the container's filesystem. You need a console appender or a separately configured file collection solution.

**Question 3.** Are `docker logs` and Kubernetes `kubectl logs` indefinite centralized retention solutions?

**Answer:** No. They depend on logs still being available on the runtime/node. For long-term search, you need a logging platform/collector and an appropriate retention policy.

**Question 4.** A Logback appender writes `ERROR` to stdout. Should the collector automatically treat it as `INFO` because the stream is stdout?

**Answer:** No. The stream is an I/O destination; severity should be based on the actual `level` field or well-founded normalization rules.

**Question 5.** In the root `INFO` example, why is `LOG.debug` not printed while `LOG.warn` is?

**Answer:** `DEBUG` is below the `INFO` threshold so the logger drops it, whereas `WARN` meets the threshold and reaches `ConsoleAppender` if no other filter blocks it.

**Question 6.** If you have two `ConsoleAppender`s with different targets, are `INFO` and `ERROR` separated automatically?

**Answer:** No. You need appropriate filters so the same event is not written to both streams. Section 8 shows one way to configure this.

**Question 7.** When running `kubectl logs --previous`, are you guaranteed to see logs from every container that restarted days ago?

**Answer:** No. `--previous` only serves logs from the previous container instance while they remain available in that Pod's context, not an infinite historical archive.

**Question 8.** Why is JSON Lines useful for container logging?

**Answer:** Each event is on a single physical line with clearly named and typed fields, making parsing easier. You still need a proper encoder and a collector configured to ingest, parse, and index it.

**Question 9.** Why shouldn't you log an access token to stdout even if the container only runs inside an internal cluster?

**Answer:** Log collection systems may store and share logs more broadly than the application itself; sensitive data must be controlled at every level.

**Question 10.** Does `AsyncAppender` guarantee that logs will never be lost when a container stops abruptly?

**Answer:** No. The queue may still hold unflushed events, drop events under overload, or lose them when the runtime kills the process; proper shutdown policies and monitoring are needed.

**Question 11.** Can you rely on the line order from `System.out` and `System.err` after a collector merges them to determine absolute execution order?

**Answer:** No. The two streams are independent with separate buffering and collection paths; use timestamps, correlation IDs, and traces for analysis.

**Question 12.** In containers, should you use `println` instead of a logging framework for all production code?

**Answer:** That should not be the default. `println` lacks levels, filters, configurable formatters/encoders, `Throwable` handling, and integrated context. A logger with `ConsoleAppender` is generally more flexible and observable.

## 18. Conclusion

**Console logging in containers** is a critical observability boundary: the Java application writes events to **stdout/stderr**, the runtime can store/expose those streams to Docker/Kubernetes commands, and a centralized collector can further parse, store, search, and alert on them.

A solid operational setup requires:

1. **Calling `Logger` instead of scattering `println`** in business code.
2. **Routing appenders/handlers to the right stream**, with clear levels and filters.
3. **Using a consistent format**, with appropriate timestamps, event codes, request/trace IDs, encoding, and `Throwable` handling.
4. **Managing logging drivers, rotation, collectors, and retention** at the infrastructure layer.
5. **Protecting sensitive data, measuring performance, and handling graceful shutdown**.

**Writing a line to the console is only the first step; you must verify the entire path from Java to the collection system so logs truly support troubleshooting and operations.**
