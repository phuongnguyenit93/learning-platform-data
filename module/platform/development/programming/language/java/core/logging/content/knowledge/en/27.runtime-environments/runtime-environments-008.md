# Container configuration for Java Logging: Docker and Kubernetes

## 1. Objectives

When deploying a Java application into a Docker container or a Kubernetes Pod, logging is no longer just about choosing INFO/DEBUG levels and a log file name. You need to decide **where logs go**, who collects and rotates logs, when configuration is passed in, whether logs persist after a container is deleted, and how to maintain correlation across logs from multiple replicas.

After this lesson, learners will be able to:

1. Configure Java logging to write events to stdout/stderr, and understand the difference between application logs and logs stored by the container runtime.
2. Pass logging levels, runtime environments, and service names into containers using environment variables or configuration files.
3. Set up Docker logging drivers and log storage limits.
4. Use ConfigMaps, env, and volumes in Kubernetes; distinguish between updating a configuration file and the application actually reloading it.
5. Collect, inspect, and handle logs when a Pod restarts, scales, gets evicted, or a node is lost.
6. Avoid common pitfalls regarding multi-line logs, JSON logs, permissions, secrets, misconfigured classpaths, and losing logs during shutdown.

The context of this lesson is **Java Core Logging in container environments**. The examples below use JDK 17 and the standard library for ease of execution, then connect those concepts to Spring Boot, Logback, and Log4j 2.

## 2. How does container logging work?

A Java application can generate logs via java.util.logging (JUL), SLF4J with Logback/Log4j 2, or another framework. In containers, the most common integration pattern is:

~~~text
Java Logger / Handler / Appender
           │
           ├── stdout (standard output)
           └── stderr (standard error)
                    │
                    ▼
             Container runtime
                    │
       ┌────────────┴────────────┐
       │                         │
     Docker                   Kubernetes
  logging driver             CRI + kubelet
       │                         │
  docker logs               kubectl logs
       │                         │
       └────────► collector ◄────┘
                        │
               central log backend
           (search, retention, alerting)
~~~

This flow has **three distinct configuration layers**:

| Layer | Configuration examples | Responsibilities |
| --- | --- | --- |
| Java application | JUL logging.properties, logback.xml, log4j2.xml, Spring Boot logging.* | Level, logger name, format, appender, MDC/trace ID, log destination |
| Container runtime / node | Docker logging driver; kubelet containerLogMaxSize, containerLogMaxFiles | Capture stdout/stderr, buffer locally, rotate logs on the node |
| Logging pipeline / backend | DaemonSet collector, OpenTelemetry Collector, Fluent Bit, centralized storage system | Enrich metadata, parse, filter, forward, retention, search/alerting |

**Do not confuse log files in the container filesystem with stdout/stderr logs.** If the application writes to /app/logs/app.log, docker logs or kubectl logs will generally not read that file automatically. To view logs through those commands, the appender must output to a stream collected by the runtime, or a separate forwarding solution must be used.

Docker json-file writes an envelope format containing log/stream/time for runtime management. That envelope **does not mean** the application's message content is already structured JSON. If you want to query by trace_id/level/service, consider logging single-line JSON produced by the application/encoder, then having the collector parse the appropriate fields.

## 3. Default strategy: one event per stdout/stderr line

For Java services running in containers, the simple and common approach is:

- Write application logs to stdout or stderr; urgency level does not necessarily dictate a specific stream, because each logging backend has its own configuration conventions.
- Use a logging framework that supports concurrent logging and emits one complete event per call.
- Configure levels per environment, limiting DEBUG/TRACE volume in production.
- Include a timestamp with an explicit timezone (usually UTC/ISO 8601) along with level, logger/service, message, and request_id/trace_id when available.
- Let the runtime/kubelet/collector manage local buffering, rotation, and shipping; do not share a single log file across multiple replicas.
- Keep information necessary for diagnostics, but avoid tokens, passwords, cookies, and sensitive personal data.

### stdout and stderr

System.out and System.err are the two standard process streams. Docker and Kubernetes typically collect both streams. However, **JUL ConsoleHandler writes to System.err by default**, even when the log level is INFO. Many other backends can write all levels to stdout via a configured console appender. Therefore, do not assume "INFO is always stdout, ERROR is always stderr".

Data in docker logs is usually an aggregation of logs stored by a supported driver from both streams. In Kubernetes, kubectl logs reads container logs via the API/kubelet. These tools do not replace long-term cluster-wide storage.

### Console JSON vs. text

Text is easy to read directly:

~~~text
INFO service=orders env=prod trace_id=... order accepted
~~~

JSON is easy to query in a collector:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","service":"orders","environment":"prod","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"order accepted"}
~~~

The two lines above illustrate formatting, not the JDK's default output. An event should form a single line with a stable structure and a trailing newline character. If a message or stack trace contains newlines, a JSON encoder should escape the content appropriately rather than breaking the record into multiple unmarked lines.

## 4. Complete example: Java 17 reading logging configuration from env

This is a **standalone program for JDK 17+**, with no Spring Boot or external library dependencies. It reads three environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| APP_LOG_LEVEL | INFO | Log threshold by JUL level name, e.g., INFO, FINE, WARNING |
| APP_ENV | local | Runtime environment name, e.g., dev, staging, prod |
| SERVICE_NAME | orders | Service name attached to log messages |

**Note:** APP_LOG_LEVEL is a name defined by **the example program itself**. JUL does not automatically read a variable named APP_LOG_LEVEL; reading the env var, parsing it, and applying the level must be done by application code or a framework.

Structure:

~~~text
container-logging-demo/
├── src/
│   └── example/
│       └── ContainerLoggingDemo.java
└── Dockerfile
~~~

**src/example/ContainerLoggingDemo.java**

~~~java
package example;

import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContainerLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ContainerLoggingDemo.class.getName());

    private static String safeTag(String name, String fallback) {
        String value = System.getenv().getOrDefault(name, fallback);
        if (!value.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid setting: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String service = safeTag("SERVICE_NAME", "orders");
        String environment = safeTag("APP_ENV", "local");

        String configuredLevel = System.getenv()
                .getOrDefault("APP_LOG_LEVEL", "INFO")
                .trim()
                .toUpperCase(Locale.ROOT);

        // An invalid level name will cause a clear error at startup.
        Level threshold = Level.parse(configuredLevel);

        // Do not forward events to the root handler to avoid duplicate printing.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(threshold);

        // JUL ConsoleHandler writes to stderr; the container runtime collects it.
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " service=" + service
                        + " env=" + environment
                        + " message=" + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            LOG.info("started");
            LOG.fine("diagnostic detail");
            LOG.warning("sample warning");
        } finally {
            console.flush();
            LOG.removeHandler(console);
            console.close();
        }
    }
}
~~~

The program is intentionally short, logging three events and then exiting so configuration can be tested easily. The `safeTag` helper restricts env values used as metadata, reducing the risk of newline characters or overly long data corrupting the log format. Production applications can use their own validation standards; do not use this regex to validate every kind of configuration value.

### Running directly on a machine with JDK

From the root directory of the example:

~~~bash
javac -encoding UTF-8 -d out src/example/ContainerLoggingDemo.java
java -cp out example.ContainerLoggingDemo
~~~

Logs written by the program to **stderr** with the default configuration:

~~~text
INFO service=orders env=local message=started
WARNING service=orders env=local message=sample warning
~~~

The FINE line does not appear because the level is currently INFO. To see FINE, set the environment variables before launching. On shells supporting POSIX syntax:

~~~bash
APP_LOG_LEVEL=FINE APP_ENV=staging SERVICE_NAME=payments java -cp out example.ContainerLoggingDemo
~~~

Output on stderr:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

On Windows PowerShell, environment variables use a different syntax, for example:

~~~powershell
$env:APP_LOG_LEVEL = "FINE"
$env:APP_ENV = "staging"
$env:SERVICE_NAME = "payments"
java -cp out example.ContainerLoggingDemo
~~~

Both launch methods run the same compiled program. **Env values are read when the process starts.** Changing shell env vars after the JVM is already running does not cause the running program to automatically update its log level.

### Correctness of the example

`LOG.setLevel(threshold)` controls event creation at the logger. `ConsoleHandler` is set to `setLevel(Level.ALL)` so the handler does not further filter events that already passed the logger. `setUseParentHandlers(false)` prevents the default root handler from printing a duplicate copy. The `Formatter` only outputs level, service, environment, and message, so output is deterministic with no random timestamps or stack traces. `ConsoleHandler` flushes automatically on publish; the `finally` block cleans up the handler upon completion. The `sample warning` data is only for observing WARNING, not indicating an actual error.

## 5. Packaging the program with a Docker multi-stage build

**Dockerfile** at the root of the example:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY src/example/ContainerLoggingDemo.java /workspace/src/example/ContainerLoggingDemo.java
RUN javac -encoding UTF-8 -d /workspace/out /workspace/src/example/ContainerLoggingDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/out /app/classes
ENV APP_LOG_LEVEL=INFO APP_ENV=local SERVICE_NAME=orders
USER 10001
ENTRYPOINT ["java", "-cp", "/app/classes", "example.ContainerLoggingDemo"]
~~~

Explanation:

- The build stage uses the JDK to compile, and the final stage uses the JRE to run, avoiding shipping the compiler in the runtime image.
- `ENTRYPOINT` in exec form (JSON array) runs the Java process directly, which is beneficial for handling stop signals and exit codes.
- `ENV` sets **defaults inside the image**; `docker run -e` and Kubernetes `env` can provide values at container creation time.
- `USER 10001` demonstrates running as non-root; the example only reads classes and writes to stderr, so no writable log directory is needed.
- The `eclipse-temurin:17-jdk` and `:17-jre` image tags may be updated over time. Production deployments should manage image versions/digests according to project policy.

Build and run (requires a running Docker Engine/Desktop):

~~~bash
docker build -t container-logging-demo:1.0 .
docker run --name log-demo \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  -e APP_LOG_LEVEL=FINE \
  -e APP_ENV=staging \
  -e SERVICE_NAME=payments \
  container-logging-demo:1.0
~~~

The container runs the program once and exits with exit code 0 if there are no errors. Output appears in the terminal running `docker run`:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

Because `--rm` was not used, you can read the logs again and then remove the container:

~~~bash
docker logs log-demo
docker inspect --format '{{.HostConfig.LogConfig.Type}}' log-demo
docker rm log-demo
~~~

The `docker logs` command displays the lines above again; it does not run the program a second time. The `inspect` command in the example returns `local` because this run specified the `local` driver. The Docker CLI supports line continuation syntax depending on the shell; on PowerShell you can enter the same `docker run` command on a single line instead of using POSIX-style backslashes.

**Do not add `-it` unless interactive input is needed**; enabling a pseudo-TTY can affect how stdout and stderr are distinguished. For typical backend services, running without a TTY is better for log collection.

## 6. Docker logging drivers, storage limits, and log lifecycle

Docker provides logging drivers such as `json-file`, `local`, `journald`, `syslog`, `fluentd`, or third-party drivers/plugins. The driver determines how Docker stores or forwards stdout/stderr; it does not replace Java appenders or logging levels.

### json-file and local

According to Docker documentation, `json-file` is the default driver for Docker Engine in many setups, primarily for backward compatibility. Without configured limits, logs can grow until they fill the disk. The `local` driver optimizes storage and has rotation enabled by default, often making it suitable for general container hosts.

Example specifying `json-file` and limits for **a single container**:

~~~bash
docker run --name log-demo-json \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  container-logging-demo:1.0
~~~

Configuring the default driver in the Docker daemon (`daemon.json` file, path depends on OS):

~~~json
{
  "log-driver": "local",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
~~~

Values in `log-opts` in the Docker daemon configuration are represented as **strings**, even for numeric-looking values. After updating `daemon.json`, reload/restart Docker according to your runtime environment's documentation. **Changing the daemon's default configuration does not automatically change the logging driver of existing containers**; new containers will receive the new configuration when created, unless overridden by options.

### Distinguish between retention and durability

`max-size`/`max-file` limits are meant to **keep log storage on the node within desired bounds**, not to guarantee long-term log retention. When a container is removed or a host fails, locally stored runtime data may be lost. To query history across multiple nodes, ship logs to a central backend and configure retention policies there.

You should also avoid directly opening the internal files Docker uses for `json-file` or `local` drivers to delete or rotate them manually; Docker manages their format and metadata. Use `docker logs`, driver settings, and compatible collection tools instead.

### Blocking, non-blocking, and log loss

Some Docker drivers/configurations support blocking or non-blocking log delivery modes. When the log destination is slow or the buffer is full, the producer may be blocked, or messages may be dropped depending on the mode and configuration. This is partially independent of async appenders in Java: there can be **queues in both the application and the runtime**.

Therefore, monitor disk usage, dropped logs, collector errors, and write latency in the actual system. Application logs do not replace an audit store that requires transactional durability.

## 7. Kubernetes: configuring with ConfigMap and env

Kubernetes typically runs multiple Pods for the same service. Each container emits logs to stdout/stderr, the runtime writes them using the CRI format, and kubelet serves `kubectl logs` and handles node-level rotation. For logs to survive beyond a Pod or node lifecycle, a cluster-level logging solution is required.

### 7.1. Runtime configuration with ConfigMap

The following example uses **the exact Docker image from section 5**. Because the demo Java program exits immediately after printing a few lines, we use a **Job** instead of a Deployment; if you used a Deployment for a run-once-and-exit program, the Pod would be restarted according to the Deployment's policy and would not properly demonstrate the learning objective.

**container-logging-k8s.yaml**

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: container-logging-settings
data:
  APP_LOG_LEVEL: "FINE"
  APP_ENV: "staging"
  SERVICE_NAME: "payments"
---
apiVersion: batch/v1
kind: Job
metadata:
  name: container-logging-demo
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: app
          image: container-logging-demo:1.0
          imagePullPolicy: IfNotPresent
          envFrom:
            - configMapRef:
                name: container-logging-settings
~~~

Explanation:

- ConfigMap stores non-secret configuration as key/value pairs.
- `envFrom` turns valid keys into environment variables in the process; Java reads them via `System.getenv`.
- The image must **actually be available in the node's container runtime**, or pushed to a registry using an image reference the Job can access. An image that only exists in your local machine's Docker is not automatically available on every Kubernetes node.
- For a default local `kind` cluster used for practice, you can load the image with `kind load docker-image container-logging-demo:1.0` before applying. For a remote managed cluster, the image needs to be in a registry with appropriate pull permissions configured.
- The Job uses `restartPolicy: Never` because this is a short-lived application. Long-lived HTTP/JVM services should use a Deployment and require a continuously running process.

Execute once the Kubernetes cluster is ready and the image is present on the node:

~~~bash
kubectl apply -f container-logging-k8s.yaml
kubectl logs job/container-logging-demo -c app
kubectl get job container-logging-demo
~~~

The expected application log lines are:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

`kubectl logs job/...` resolves to the corresponding Pod of the Job; if it has not finished yet, you may need to check the Pod status and retry after its container has been created. If no logs appear, check for image pull errors, Pod events, and the namespace before concluding that Java logging is broken.

**Update note:** changing data in a ConfigMap **does not automatically change the env vars of a running Pod**. For Deployment-based applications, you need a redeploy/rolling restart so new Pods receive the new env vars. For a completed Job, to run again with new values you must create a new execution appropriately, rather than expecting the old Job to restart on its own.

### 7.2. Mounting configuration files from a ConfigMap

Some applications using Logback/Log4j 2/JUL must read XML or `.properties` files instead of relying solely on env vars. In that case, you can mount a ConfigMap as files inside the container.

**Example for Spring Boot using Logback**:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-logback
data:
  logback-spring.xml: |
    <configuration>
      <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
          <pattern>%d{ISO8601} %-5level service=orders %logger - %msg%n</pattern>
        </encoder>
      </appender>
      <root level="INFO">
        <appender-ref ref="CONSOLE"/>
      </root>
    </configuration>
~~~

The Deployment snippet below illustrates how a Spring Boot app **already packaged in the image** picks up that file; the image must contain a real Boot application, not the small Java program from section 4:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: app
          image: registry.example.com/orders:1.0
          env:
            - name: LOGGING_CONFIG
              value: "file:/etc/app/logging/logback-spring.xml"
          volumeMounts:
            - name: logging-config
              mountPath: /etc/app/logging
              readOnly: true
      volumes:
        - name: logging-config
          configMap:
            name: orders-logback
~~~

The image and registry in the Deployment manifest are **architectural examples**; they must be replaced with an actual published and accessible Spring Boot image before deploying. The snippet omits health checks, resource limits, and networking since those depend on the specific application.

Kubernetes projects each ConfigMap key as a file under `mountPath`; with the ConfigMap in the example, the file is `/etc/app/logging/logback-spring.xml`. Spring Boot uses `LOGGING_CONFIG` to select the corresponding logging configuration at startup.

**Important notes:**

- A ConfigMap mounted as a volume may be updated by kubelet **after some delay** when the ConfigMap changes. This **does not guarantee** the logging backend will reload automatically; the application might only load the configuration once at startup.
- If you use `volumeMount` with `subPath` pointing to a single key, the mounted file will **not receive automatic ConfigMap updates** through the normal mechanism.
- Configuration passed via Pod env vars does not update automatically when the ConfigMap changes. A rolling restart is usually the most controllable way to roll out changes.
- Some Spring Boot configuration extensions are incompatible with Logback's direct scan/reload mechanism; do not enable `scan` expecting ConfigMap changes to take effect without checking the backend documentation.
- Use ConfigMap for non-sensitive content; use Secrets and appropriate secret-management mechanisms for sensitive data. Avoid putting passwords or tokens into log patterns or MDC.

## 8. Connecting to real-world Java logging frameworks

### 8.1. Java Util Logging

JUL has `ConsoleHandler` which writes to stderr. A `logging.properties` configuration file can be selected at JVM startup via:

~~~bash
java -Djava.util.logging.config.file=/etc/app/logging.properties -jar app.jar
~~~

Here `/etc/app/logging.properties` must exist and use JUL syntax. If the container uses a Kubernetes ConfigMap to mount the file, mount it to this path and pass the appropriate system property.

**Example JUL configuration file:**

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s %5$s%n
~~~

This example is for applications using JUL where JUL initializes loggers/handlers from `LogManager`. The `ContainerLoggingDemo` program in section 4 **creates its own `ConsoleHandler` and overrides format/level in code**, so do not use this properties file example to replace its behavior. When an application uses a complex launcher or entrypoint, verify that `-D` options reach the JVM before loggers are initialized.

### 8.2. Logback and Log4j 2

For Java using SLF4J + Logback, configure `logback.xml`/`logback-spring.xml` per environment, using `ConsoleAppender` with an appropriate encoder. When running Spring Boot, `logback-spring.xml` is supported by Boot; standalone Logback typically looks for `logback.xml`/`logback-test.xml` or a path specified by `logback.configurationFile`.

For Log4j 2, use `log4j2.xml`/`log4j2-spring.xml` depending on the runtime mode, with a Console appender and an appropriate PatternLayout/JSON layout. The path can be specified via `log4j2.configurationFile` in plain Java applications. Do not mix Logback XML syntax with Log4j 2 XML, and do not use two primary backends simultaneously without a clear design.

Concise Logback `ConsoleAppender` example:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger trace_id=%X{trace_id:-} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

This is an **XML configuration**, not a standalone runnable Java program. MDC keys such as `trace_id` only have values if the app or tracing instrumentation actually provides that context. A pattern containing a `trace_id` placeholder does not create distributed tracing on its own.

### 8.3. Spring Boot: environment variables and structured logging

Spring Boot supports mapping properties from the environment, for example:

~~~text
LOGGING_LEVEL_ROOT=INFO
SPRING_APPLICATION_NAME=orders
~~~

In Spring Boot versions that support built-in structured logging, you can select ECS JSON on the console with:

~~~properties
logging.structured.format.console=ecs
~~~

Or configure the equivalent via env:

~~~text
LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs
~~~

Support for this property **depends on the Spring Boot version**; it is not a default feature of every version or of standalone JUL. If the application already provides a custom `logback-spring.xml`/`log4j2-spring.xml`, verify that the corresponding encoder/layout actually uses Boot's structured logging configuration; a hand-written custom console appender does not automatically switch to JSON just because the env var is present.

Setting the root level via `LOGGING_LEVEL_ROOT` is usually more convenient than editing files inside the image for each environment. For package/class-level logging, check the property binding rules of your Spring Boot version, especially since logger names are case-sensitive.

## 9. Kubernetes: log rotation and retrieval on restarts

### 9.1. kubectl logs is only a window into node logs

The Kubernetes kubelet manages container log paths and rotation according to node configuration. Two common parameters are:

~~~yaml
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
~~~

These are **kubelet configuration** keys, not application Deployment specs or Java environment variables. Default values are commonly documented by Kubernetes as 10Mi and 5, though a managed cluster may configure them differently. Do not put these values into a Pod manifest if you do not have access to configure kubelet.

According to Kubernetes documentation, `kubectl logs` normally reads the latest log file provided by kubelet; previously rotated logs are not necessarily viewable via that command. If a container in a Pod has been restarted, you can try:

~~~bash
kubectl logs pod/orders-abc123 -c app --previous
~~~

The Pod name `orders-abc123` is illustrative only. The `--previous` flag requests logs from the previous instance of the container, provided that instance and its logs are still retained on the node. It is not an archive of all restarts and cannot recover logs from a deleted/evicted Pod or a lost node.

To inspect running Pods:

~~~bash
kubectl get pods -l app=orders
kubectl logs deployment/orders -c app --tail=100
kubectl logs deployment/orders -c app --since=10m
~~~

Using `deployment/...` is only convenient when a single appropriate Pod/container can be selected. When running multiple replicas and needing to view **all** of them, query using a label selector with appropriate limits/concurrency for your `kubectl` version, or better yet, use a centralized backend for aggregation.

### 9.2. Cluster-level logging

Production systems typically deploy a node-level collector (such as a DaemonSet) to read container logs, enrich them with metadata like namespace, pod, container, and node, and ship them to independent storage. Some systems use a sidecar when an application can only write to files or requires special processing.

Responsibilities should be clearly defined:

- The application decides business fields and message sensitivity.
- The runtime/kubelet manages stream capture and local rotation.
- The collector handles parsing, metadata enrichment, batching, retries, and forwarding.
- The backend enforces retention, search access control, querying, and alerting.

Do not assume that because `kubectl logs` shows output, data has already been centrally collected, or that all logs will certainly survive a crash.

## 10. Multi-line, JSON, trace context, and timestamps

### 10.1. Multi-line events

Java stack traces are naturally multi-line:

~~~text
ERROR failed to process order
java.lang.IllegalStateException: invalid state
    at example.OrderService.process(OrderService.java:42)
    at example.App.main(App.java:10)
~~~

These lines are illustrative. In a logging pipeline, a multi-line log record can be treated by the runtime/collector as multiple separate log lines if there is no mechanism to merge them. Use a formatter/encoder and collector configuration that preserve the event; many systems support structured JSON containing the message/exception as a single newline-escaped field. Do not solve this by stripping stack traces from all errors.

### 10.2. Correlation information

Consistent fields should be included, such as:

~~~text
service.name=orders
environment=prod
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
request_id=req-42
~~~

Trace IDs and span IDs must come from a valid tracing context; do not assign arbitrary strings and claim it is distributed tracing. With thread pools, `CompletableFuture`, or reactive frameworks, proper context propagation and cleanup mechanisms are required. MDC/ThreadLocal can help attach IDs to logs, but **they do not automatically propagate across the network or asynchronous threads**.

Pod/node/namespace information can be enriched by the collector from Kubernetes metadata; the application does not necessarily need to hard-code the Pod name into every log line. Use `service.name` and `environment` to query consistently across multiple replicas.

### 10.3. Timestamps

Prefer timestamps with an explicit timezone. Timestamps recorded by the application event, runtime, and collector may differ due to buffering, network delay, or clock skew between nodes. Do not infer exact causality solely from the display order of lines in the backend. Distributed tracing analysis relies on span relationships and proper correlation IDs.

## 11. Shutdown, configuration reload, and performance

### 11.1. Graceful shutdown

When Kubernetes terminates a Pod or Docker stops a container, the process typically receives a stop signal (per runtime configuration) before being forcefully killed if the grace period expires. For Java, you should:

- Ensure the JVM receives signals properly (exec-form `ENTRYPOINT` or an entrypoint that forwards signals).
- Stop accepting new work and finish in-flight work that can complete within the grace period.
- Flush/close async logging appenders according to the backend lifecycle to avoid losing queued logs.
- Monitor timeouts, exceptions, and forceful kills to understand log delivery guarantees and limits.

**Do not confuse `logger.info()` returning with the log having reached the central backend.** With an async appender or network sink, events may still be sitting in a buffer. A forceful kill, crash, or node failure can lose unforwarded events.

### 11.2. Reloading logging configuration

Configuration sources have different lifecycles:

| Source | When it changes | Common effect |
| --- | --- | --- |
| ENV in Docker/Kubernetes Pod | When a new container/Pod is created | Existing process does not receive new env values |
| File mounted from ConfigMap volume | After a kubelet sync delay | File may update, but app only changes behavior if it actually re-reads/reloads |
| Configuration baked into image | After rebuilding image/deploying new version | Old containers do not change files automatically |
| Logging level updated via management API | At runtime if supported by framework | Can change level immediately; requires access control and lifecycle management |
| Collector/backend settings | After the pipeline is updated | Can change filtering/parsing/retention without changing Java code |

A logging configuration change can affect CPU load, I/O, storage, and cost. Enabling DEBUG/TRACE across all of production without a time limit or filter can generate huge volumes of data. When debugging an incident, enable only the specific logger/package needed and turn it off once the information is collected.

### 11.3. Performance and backpressure

- Parameterized logging can reduce string construction cost when a level is disabled, but it does not make reading shared state thread-safe.
- Synchronous logging to the console can block when downstream is slow. Async logging has its own queue, requiring policies for queue-full behavior and shutdown flushing.
- The container runtime also has buffers and drivers; the collector adds retries/batching. Measure the entire pipeline, not just individual logger call benchmarks.
- Set quotas and retention at the appropriate storage tier; monitor drop rates, queue depth, stdout/stderr throughput, and node disk pressure.

## 12. Security and production operations

### 12.1. Do not log secrets

Do not log access tokens, passwords, private keys, session cookies, payment data, or full request bodies containing sensitive information. ConfigMaps are not meant for secrets; even when using a Kubernetes Secret, **do not** assume Secret contents are safe to write to logs. Environment variables can be exposed through diagnostic dumps or command output; protect configuration read permissions and avoid printing all of `System.getenv()`.

### 12.2. Non-root users and read-only root filesystems

Containers often run as a non-root user and may set `readOnlyRootFilesystem: true`. Writing to stdout/stderr does not require a writable log directory in the image. If an appender tries to write to `/var/log/app.log` or `logback.xml` points to an unauthorized path, the log file may fail to be created; this is a path/permission error, not a logging level issue.

If writing to files is strictly required, mount an appropriate volume, grant permissions to the process UID, manage rotation/retention, and define how the collector reads the files. In a multi-replica environment, avoid sharing a single log file across multiple JVMs and treating it as an ordered stream.

### 12.3. Clear configuration hierarchy

An easy-to-operate design order:

1. The image contains safe default configuration (INFO, console output).
2. The deployment platform passes env vars for values that differ by environment.
3. ConfigMap mounts XML/`.properties` files when complex appender/format configuration is needed.
4. The runtime/kubelet manages local logs; the collector ships logs to the backend.
5. Retention policies and log access permissions are set at the backend/cluster according to system requirements.

This is a separation of responsibilities, not a rigid override order that applies to every logging framework. Logback, Log4j 2, JUL, and Spring Boot have different file/property resolution mechanisms; always rely on the actual backend to determine precedence.

## 13. Troubleshooting: common container issues

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `docker logs` shows nothing even though `/app/logs` has files | App writes to files in container filesystem | Switch to `ConsoleAppender`/`ConsoleHandler`, or set up a forwarder/collector for files |
| `kubectl logs` is empty | Pod not running, wrong container, logs only written to file, blocked by logging level, driver has no data | Check `get pod`, `describe`, container `-c`, log level, and sink |
| Edited ConfigMap but level did not change | ENV does not auto-update, app only reads file at startup, `subPath` used | Create new Pod/rollout, verify whether reload is actually supported |
| INFO appears on stderr | JUL `ConsoleHandler` uses stderr by default | Understand the handler's stream; still collectible via Docker/Kubernetes |
| Old logs are missing | Container/Pod deleted, logs rotated, node lost, no central backend | Check node retention/collector; build cluster-level logging |
| Node disk full | Unlimited `json-file`, self-written file appender, excessive DEBUG | Enable rotation, lower level, monitor disk/retention |
| Logs split into multiple records | Multi-line stack trace, collector misparsing | Use JSON encoder or explicitly configured multi-line parser |
| Trace/request IDs mixed between tasks | MDC not properly propagated/cleared when using thread pools | Capture and restore context in the right scope; use proper instrumentation |
| Works locally but fails in container | Config file not on runtime classpath, case sensitivity, wrong path or permissions | Check image contents/working directory, config path, and file permissions |
| Log costs spike after deploy | DEBUG/TRACE enabled, large request payloads, high-cardinality fields | Restrict log levels, filter data, measure throughput and cost |
| Logs disappear when Pod stops | Async buffer not flushed or killed too quickly | Configure graceful shutdown and appropriate flush timeout |

### Suggested inspection sequence

1. Read logs at **the layer closest to the application**: are logs actually being emitted to stdout/stderr?
2. Identify which backend/config file is active (JUL, Logback, Log4j 2, Spring Boot).
3. For Docker: check `docker logs`, `docker inspect` logging driver, and `max-size`/`max-file`.
4. For Kubernetes: check Pod, container name, events, `kubectl logs`, and `--previous` on restarts.
5. If container has logs but the central backend does not: check the collector, parsing, quota/queue, network, credentials, and shipping errors.
6. If logs are missing during shutdown: check process lifecycle, grace period, and flushing.
7. Verify in a test environment with production-like configuration; avoid turning on DEBUG broadly on a cluster serving users.

## 14. Practice exercises

### Exercise 1: Compare environments

Build the Docker image from section 5 and run it sequentially with `APP_LOG_LEVEL=INFO` and `FINE`. Record the count and order of events; explain why the same image produces different output when creating a new container.

### Exercise 2: Rotation

Run the image with the Docker `local` driver and `max-size`/`max-file` limits. Increase the log volume in a separate demo in a test environment and inspect the configuration with `docker inspect`. Compare with an explicitly limited `json-file` driver and distinguish Docker's storage usage from application-written files.

### Exercise 3: Kubernetes ConfigMap

Use the Job and ConfigMap from section 7. Run with `APP_ENV=staging`, then change the ConfigMap to `prod`. Explain why the completed Job does not automatically update its value and how to create a new run to verify the new configuration.

### Exercise 4: Logback configuration file

In a real Spring Boot application using Logback, mount a `logback-spring.xml` file from a ConfigMap, point `LOGGING_CONFIG` to the file, and observe console logs. After updating the ConfigMap, confirm that the mounted file updates, then try a rolling restart. Compare the behavior between "the file changed" and "the logging framework changed its level".

### Exercise 5: Investigate lost logs

Suppose a service restarts multiple times and only the most recent logs remain in `kubectl logs`. Draw the layers appender → runtime → kubelet → collector → backend, marking where data can be retained or lost. Propose monitoring for queues, dropped logs, and appropriate retention.

## 15. Key takeaways

**Container configuration for Java Logging** is a coordination between application configuration, container runtime, and collection infrastructure. For typical services, start with console logging to stdout/stderr, configure levels via env or mounted files, bound local logs via Docker/kubelet, and use a centralized collector/backend when durable history is needed. Always verify that the application actually reads/reloads configuration, especially when a ConfigMap changes. A log line appearing in `docker logs` or `kubectl logs` does not prove it has been stored long-term.

### Official references

- Kubernetes – Logging Architecture: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes – ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes – Configure a Pod to Use a ConfigMap: https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/
- Kubernetes – Updating Configuration via a ConfigMap: https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/
- Docker – Configure Logging Drivers: https://docs.docker.com/engine/logging/configure/
- Docker – Local File Logging Driver: https://docs.docker.com/engine/logging/drivers/local/
- Docker – JSON File Logging Driver: https://docs.docker.com/engine/logging/drivers/json-file/
- Docker – Multi-stage Builds: https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/
- Oracle JDK 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle JDK 17 – LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
