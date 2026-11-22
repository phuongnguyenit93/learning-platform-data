# Container Log Collection in Java: From stdout/stderr to Centralized Logging

## 1. What Does Container Log Collection Mean?

When running a Java application in Docker or Kubernetes, logs no longer reside solely in a fixed local file or terminal. A container can be restarted, replaced, rescheduled to another node, or deleted after a deployment. If an operator only opens a terminal to watch log lines as they appear, it is very easy to lose context when an error occurs.

**Container log collection** is the process of forwarding events emitted by an application — typically via **stdout** and **stderr** — to a place where they can be **stored, queried, analyzed, and alerted on** independently of the container lifecycle.

The goals of this lesson are to understand:

1. How a Java application should **emit logs** inside a container.
2. How the container runtime and Docker logging drivers **capture stdout/stderr**.
3. What roles Kubernetes kubelet and the **CRI container logs** format play.
4. How **node-level agents, sidecars, and direct pushing** differ.
5. How to choose between **single-line text or JSON Lines**, add metadata, and handle stack traces.
6. How to manage **rotation, buffering, log loss or duplication, security, and cost**.
7. How to run a Java 17 example in Docker and observe it with `docker logs`, along with a verifiable Pod deployment approach on a test cluster.

### Distinguishing Three Responsibilities

| Responsibility | Typical Owner | Evidence |
| --- | --- | --- |
| **Emitting logs** | Java application and logging framework | `System.out`, `System.err`, Logger/Appender |
| **Short-term storage near the container** | Container runtime, logging driver, kubelet | Local logs on the node, `docker logs`, `kubectl logs` |
| **Centralized collection and storage** | Agent/collector and backend | Data remains queryable after restarts, reschedules, or node failures |

**Seeing a log line in `docker logs` or `kubectl logs` does not prove that the event has been durably stored in a centralized system.** Those two commands primarily serve to retrieve logs currently held by the runtime or kubelet.

## 2. Typical Flow from Java to the Collector

```text
Java service
   |
   +-- LOG.info(...) / LOG.error(...)
   |        |
   |        v
   |   Logger + Level + Filter
   |        |
   |        v
   |   Console Appender/Handler + Layout
   |        |
   +---- stdout / stderr
                 |
                 v
           Container runtime
                 |
                 v
         Local container log
         (driver or CRI file)
                 |
                 v
          Node logging agent
          (DaemonSet/collector)
                 |
           Parse + enrich + batch
                 |
                 v
          Central log backend
                 |
                 v
       Search / dashboard / alert
```

Each layer has a distinct responsibility:

- **Logger** receives events, `INFO`/`WARN`/`ERROR` levels, and parameters.
- **Console Appender/Handler** writes data to a standard stream.
- **Layout/Encoder** produces a text string or JSON; it does not decide where logs are durably stored.
- **Container runtime** redirects stdout/stderr to the configured logging mechanism.
- **Collector** reads logs, decodes the format, enriches metadata, and sends them to the backend.
- **Backend** manages indexing, retention, access control, querying, and alerting.

The flow above is a typical architecture, not a mandate that every application must use the exact same components. An application can send logs directly via OTLP/HTTP or a socket, or a sidecar can read a shared file. However, **stdout/stderr + node-level agent** is the easiest option to operate for many containerized applications.

## 3. stdout and stderr in Containers

In Java, the standard streams are `System.in`, `System.out`, and `System.err`. For logging, the two important streams are:

- **stdout**: typically used for normal output or application logs collected by the runtime.
- **stderr**: typically used for error messages or diagnostics.
- **Level vs. stream**: an `ERROR` event can still be written to stdout by a Console Appender; a JUL `ConsoleHandler` `INFO` event goes to stderr by default.

When running a container, the runtime can capture **both stdout and stderr**. For example, `docker logs` typically displays data from both, so the order seen in a terminal **is not proof** of which stream each line originated from.

A useful design rule:

- For **long-running Java services**, configure an appender to write accepted logs as single-line text or JSON to stdout. If splitting streams by level is required, design filters carefully to avoid duplicates.
- For **CLIs that output JSON or machine-readable data on stdout**, do not mix text logs into data stdout. Write diagnostics to stderr or another channel.
- Do not scatter `System.out.println` calls as a substitute for a full logging framework: it does not automatically provide filtering, timestamps, thread names, logger names, exception causes, or unified configuration.

**JUL note:** `java.util.logging.ConsoleHandler` writes to `System.err` by default. To use JUL with stdout, you can use `StreamHandler(System.out, formatter)` with controlled lifecycle and flushing; `StreamHandler.close()` may close the underlying stream. In frameworks such as Log4j2 or Logback, a ConsoleAppender can target stdout directly via configuration.

## 4. Java 17 Example Running Standalone and in Docker

This example intentionally **uses no logging libraries outside the JDK** to focus on demonstrating **the stdout/stderr journey**. The code emits three single-line JSON events: two to stdout and one to stderr. The JSON strings are **fixed constants for deterministic output**, not a guide to concatenating user input into JSON. Real applications should use a dedicated encoder/logger.

### 4.1. `ContainerLogDemo.java`

```java
public final class ContainerLogDemo {
    private ContainerLogDemo() {
    }

    public static void main(String[] args) {
        System.out.println(
                "{\"level\":\"INFO\",\"event\":\"application_started\","
                + "\"service\":\"orders\"}");

        System.err.println(
                "{\"level\":\"WARN\",\"event\":\"dependency_slow\","
                + "\"service\":\"orders\",\"duration_ms\":250}");

        System.out.println(
                "{\"level\":\"INFO\",\"event\":\"order_processed\","
                + "\"service\":\"orders\",\"order_id\":\"ORD-101\","
                + "\"outcome\":\"SUCCESS\"}");
    }
}
```

Run directly with JDK 17 or later:

```bash
javac -encoding UTF-8 ContainerLogDemo.java
java ContainerLogDemo
```

**Exact stdout, in order within stdout:**

```json
{"level":"INFO","event":"application_started","service":"orders"}
{"level":"INFO","event":"order_processed","service":"orders","order_id":"ORD-101","outcome":"SUCCESS"}
```

**Exact stderr:**

```json
{"level":"WARN","event":"dependency_slow","service":"orders","duration_ms":250}
```

If a terminal merges both streams when displaying them, the `WARN` line may appear between the two `INFO` lines, or the display order may vary because the two streams are captured independently. **Do not assert a total ordering between stdout and stderr** solely from the order of `println` calls.

You can verify this in a Linux/macOS shell:

```bash
java ContainerLogDemo > stdout.log 2> stderr.log
cat stdout.log
cat stderr.log
```

The two files receive the exact lines belonging to each stream. `stdout.log` and `stderr.log` are files created by **shell redirection**, not opened by Java code via `FileWriter`.

### 4.2. `Dockerfile`

In the same directory as `ContainerLogDemo.java`, create a `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /src
COPY ContainerLogDemo.java .
RUN javac -encoding UTF-8 ContainerLogDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/ContainerLogDemo.class .
ENTRYPOINT ["java", "-cp", "/app", "ContainerLogDemo"]
```

This is a **multi-stage build**:

1. The `build` stage uses JDK 17 to compile.
2. The runtime stage uses JRE 17 and copies only the compiled `ContainerLogDemo.class`.
3. The JSON array form of `ENTRYPOINT` runs Java directly without spawning an intermediate shell just to start the process.
4. Java still writes to the process's stdout/stderr inside the container, and the Docker runtime captures those streams.
5. In this example, the application writes no log files inside the container; therefore, stopping or deleting the container does not alter event formatting logic.

This build uses public Eclipse Temurin image tags; tag contents can update over time. For bit-for-bit reproducible builds or supply-chain control, pin image digests and verify base image sources according to your project's policies.

### 4.3. Building and Running with Docker

Requires a running Docker Engine/Desktop with permission to run containers:

```bash
docker build -t container-log-demo:1.0 .
docker run --name java-log-demo \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  container-log-demo:1.0
```

In PowerShell, you can place the `docker run` command on **a single line** instead of using backslashes for line continuation:

```powershell
docker build -t container-log-demo:1.0 .
docker run --name java-log-demo --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 container-log-demo:1.0
```

Wait for the container to exit (the demo program runs very briefly), then run:

```bash
docker logs java-log-demo
docker logs --timestamps java-log-demo
docker inspect --format '{{.HostConfig.LogConfig.Type}}' java-log-demo
docker rm java-log-demo
```

`docker inspect` is expected to show `json-file` because the run command selected that driver. `docker logs` typically displays all three JSON lines emitted by the application (without the `json-file` wrapper), though **the interleaved order of stdout and stderr should not be treated as invariant**. `--timestamps` adds timestamps from runtime metadata, not generated by Java code.

Do not pass `--rm` in `docker run` if you want to run `docker logs java-log-demo` **after** the process finishes; that flag can remove the container before you inspect the logs. Clean up with `docker rm` after verification.

**Output from `docker build`, image pulls, and Docker messages** depend on the environment. The strings you can assert deterministically are the stdout/stderr of the **Java program** in Section 4.1; do not treat the entire Docker CLI output as a fixed string.

## 5. What Is a Docker Logging Driver?

Docker provides **logging drivers** to capture and route container output. When unspecified, Docker Engine commonly defaults to **`json-file`**; you can check the actual configuration with:

```bash
docker info --format '{{.LoggingDriver}}'
```

Common drivers:

| Driver | Characteristics | Notes |
| --- | --- | --- |
| `json-file` | Stores each container's stdout/stderr as internal JSON records | Common default; requires rotation to avoid filling the disk when logs are heavy |
| `local` | Stores local logs in a more space-efficient format | Recommended by Docker for many standalone Docker Engine setups; has default rotation |
| `journald` | Sends logs to the systemd journal | Depends on OS configuration and permissions |
| `syslog` | Forwards logs to syslog | Requires endpoint and protocol configuration |
| `fluentd` | Forwards logs to a Fluentd collector | Depends on the collector and failure policy |
| `gelf` | Sends logs in Graylog Extended Log Format | Collector must accept the matching protocol |
| `none` | Writes no logs via a Docker driver | `docker logs` has no logs to return for that container |

Driver choice affects how `docker logs` and collection tools retrieve logs. **Do not read or modify Docker logging driver internal files directly** from application scripts; Docker manages these files and external manipulation can cause unexpected behavior.

### `json-file` Is a Runtime Wrapper, Not Application JSON

When using `json-file`, an internal record looks like this (illustrative):

```json
{
  "log": "{\"level\":\"INFO\",\"event\":\"application_started\",\"service\":\"orders\"}\n",
  "stream": "stdout",
  "time": "2026-11-09T12:00:00.000000000Z"
}
```

Here:

- `log` contains **the data printed by the application**, which itself is a JSON string.
- `stream` indicates whether the data came from `stdout` or `stderr`.
- `time` is a timestamp added by the driver/runtime (the timestamp value here is illustrative).
- The outer JSON object **does not mean the collector has deeply parsed** the JSON string inside the `log` property into `event` and `service` fields.

A pipeline typically needs two stages: **unwrap the runtime wrapper**, then **parse the application payload** if the payload is structured JSON. If `log` is stored only as a string, dashboards cannot automatically query `order_id` as a separate field.

### Configuring Rotation to Avoid Filling the Disk

Example for Docker Engine `daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

In `daemon.json`, `log-opts` values are **strings**, including `"3"`. Default daemon settings typically apply only to **newly created containers** after the configuration takes effect; existing containers do not automatically pick up the new settings. How configuration changes and daemon restarts are performed depends on the administrative environment.

Official Docker documentation notes that `json-file` is the default for compatibility reasons and **has no rotation enabled by default** in many setups; for standalone Docker Engine, the `local` driver with default rotation is worth considering. However, if a platform already runs a specific pipeline or kubelet setup, do not change the driver without checking runtime requirements.

**Rotation is a local storage limit**, not a mechanism for syncing data to a central store. If the collector cannot keep up before old files are deleted, some logs can be lost.

## 6. Docker Blocking vs. Non-Blocking: Reliability Trade-offs

Docker logging drivers deliver output in **blocking** or **non-blocking** mode depending on the driver and configuration.

- **Blocking** is the common default: when the driver or destination is slow, writing to stdout/stderr can block, impacting the application's execution path.
- **Non-blocking** routes records through a bounded intermediate buffer; when the buffer fills up, new records may be **dropped** instead of blocking the application.
- **Non-blocking does not mean "never blocks and never drops logs."** You must choose between application latency, log durability, and observability.

Docker example with `json-file`:

```bash
docker run --name buffered-log-demo \
  --log-driver json-file \
  --log-opt mode=non-blocking \
  --log-opt max-buffer-size=4m \
  container-log-demo:1.0
```

This is an **illustrative command**, not a recommendation to enable non-blocking by default for every system. With a very short demo, it is hard to reproduce a full buffer; controlled load testing is needed to observe the trade-off.

Operational questions to answer:

1. Is losing a few `DEBUG` lines acceptable?
2. Would losing an `ERROR` event impair critical incident investigation?
3. If the collector is congested, are HTTP requests allowed to slow down because of logging?
4. Are there metrics/alerts for dropped logs, queue occupancy, retries, and ingestion rate?
5. Is a separate **durable audit/event store** required for mandatory events?

In real systems, **observability logs** and **transaction evidence** should not be conflated. The fact that `LOG.info("payment_completed")` executed does not prove that payment data was committed or that the collector durably stored the event.

## 7. How Kubernetes Collects Container Logs

In Kubernetes, the container runtime captures container stdout/stderr, while kubelet exposes logs through the API; the common command is `kubectl logs`. Kubelet and the runtime use the **Container Runtime Interface (CRI)** logging mechanism.

Kubernetes documentation notes:

- The simplest application logs typically go to container **stdout/stderr**.
- By default on Linux, kubelet directs the runtime to write container logs under `/var/log/pods` on the node.
- Kubelet manages **log rotation** according to configured parameters.
- `kubectl logs` typically reads from local node logs; it is **not a cluster-level storage system**.
- If a Pod is evicted or a node is lost, local logs may disappear with the node/Pod lifecycle.
- For long-term retention and cross-node querying, a **dedicated storage backend** is required, such as a pipeline with an agent/collector.

```text
Pod: orders-api container
      |
 stdout/stderr
      |
      v
Container runtime + CRI log
      |
      v
Node local log files
  /var/log/pods/...
      |
      +--> kubelet API --> kubectl logs
      |
      +--> DaemonSet agent
                    |
                    v
            Central collector/backend
```

A common misconception: `kubectl logs` can present both stdout and stderr in a single output stream. Whether streams can be queried separately depends on the version and enabled features; do not assume the default command identifies which stream each line came from without metadata.

### CRI Container Log Format

A local CRI record has the conceptual format:

```text
<timestamp> <stream> <tag> <content>
```

Example:

```text
2026-11-09T12:00:00.123456789Z stdout F {"level":"INFO","event":"application_started","service":"orders"}
2026-11-09T12:00:00.223456789Z stderr F {"level":"WARN","event":"dependency_slow","service":"orders","duration_ms":250}
```

This is an **illustrative example of a file written by the runtime on the node**, not raw Java stdout or exact `kubectl logs` output.

- `timestamp`: time recorded by the runtime, typically in high-precision RFC 3339 format.
- `stdout` / `stderr`: source stream.
- `F`: full record according to CRI framing.
- `P`: **partial** fragment when a record is split; the collector must handle fragments to avoid producing malformed events.
- `content`: application payload, which may be single-line text or JSON.

Do not use a regex starting with `"{"` to parse CRI files from the start of the line: timestamp/stream/tag precede the payload. The collector needs a **container log format parser** first, and then an application JSON parser if you want separate fields.

## 8. Running an Example on a Kubernetes Pod

The `Dockerfile` in Section 4 built the image `container-log-demo:1.0`. To run on Kubernetes, that image must be **available to the nodes**: pushed to a registry accessible by the cluster or loaded into a test cluster such as kind.

### 8.1. `pod.yaml` Manifest

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-log-demo
  labels:
    app: java-log-demo
spec:
  restartPolicy: Never
  containers:
    - name: demo
      image: container-log-demo:1.0
      imagePullPolicy: IfNotPresent
```

This is a **simple test Pod**, not a Deployment for a continuous service. It runs Java and exits, so the Pod phase may become `Succeeded`; no Service, port, or volume is needed.

If using **kind** and the image was built in local Docker:

```bash
kind load docker-image container-log-demo:1.0
kubectl apply -f pod.yaml
kubectl get pod java-log-demo
kubectl logs pod/java-log-demo -c demo
kubectl logs pod/java-log-demo -c demo --timestamps
```

The `kind load docker-image` command assumes kind is installed and you are targeting the default kind cluster. If your cluster has a different name, specify the target cluster. For Kubernetes outside kind, push the image to a registry the nodes can pull from and update `image` in the manifest; **do not** expect a remote cluster to see an image that only exists on your laptop.

`kubectl logs` will typically contain the application's three JSON messages as stored locally, but **do not assert a fixed interleaving order between the two streams or fixed timestamps**. If the Pod fails to run with `ImagePullBackOff`, check image distribution and registry access rather than blaming logging first.

When finished testing:

```bash
kubectl delete pod java-log-demo
```

After deleting the Pod, do not treat that Pod's local logs as a long-term store. If you need to inspect events after a Pod is deleted, a cluster-level logging solution must have collected them beforehand.

### 8.2. Useful Inspection Commands

```bash
kubectl logs pod/java-log-demo -c demo
kubectl logs pod/java-log-demo -c demo --timestamps
kubectl logs pod/java-log-demo -c demo --tail=50
kubectl logs pod/java-log-demo -c demo --since=10m
```

For a long-running service, `kubectl logs -f` follows new logs. If a container has a previous run after a restart, `kubectl logs --previous` can retrieve logs from the previous instance **if kubelet still retains that file**. It is not an archive of every container instance that ever ran.

**Important limitation:** Current Kubernetes documentation notes that `kubectl logs` only serves the contents of the container's **current latest log file** as managed by kubelet, even when the node has rotated multiple files. Do not use `kubectl logs` output to assume the entire log history is still present. An evicted Pod can lose local logs, and a node failure can make logs inaccessible.

## 9. Rotation and Retention in Kubernetes

Kubelet manages container log file rotation based on configuration. Common fields:

| Kubelet Configuration Field | Meaning | Default Value Stated in Kubernetes Docs |
| --- | --- | --- |
| `containerLogMaxSize` | Maximum size of each container log file | `10Mi` |
| `containerLogMaxFiles` | Number of log files retained per container | `5` |
| `containerLogMaxWorkers` | Concurrency level for rotation work | Depends on configuration/version |
| `containerLogMonitorInterval` | Interval for checking rotation | Depends on configuration/version |

These values are **reference documentation defaults** and must not be used to guess the settings of a live cluster. Administrators can customize them, and environments vary across configurations and releases.

For example, if an application writes 40 MiB and the node rotates at 10 MiB, `kubectl logs` may return only the contents of the latest file rather than all 40 MiB.

Distinguish between:

- **Rotation:** limiting log file disk usage on the node.
- **Backend retention:** policy governing how long data sent by the collector is kept in the central system.
- **Sampling/drop policy:** deciding which records are kept or discarded at processing layers.
- **Backup/audit:** ensuring critical data is preserved; not synonymous with normal rotation or retention.

Do not directly edit CRI files managed by the runtime/kubelet to "fix" logs. Agents should use a tailer/parser compatible with rotation and track offsets according to policy.

## 10. Three Log Collection Patterns in Kubernetes

Kubernetes describes three common approaches for cluster-level logging.

| Pattern | How It Works | Advantages | Trade-offs |
| --- | --- | --- | --- |
| **Node-level agent / DaemonSet** | One agent per node reads logs from containers on that node | No application code changes; shares collection overhead across Pods | Requires host log read access, parsers, buffering, and security configuration |
| **Sidecar logging container** | Helper container reads an app's files/sockets or forwards dedicated logs to stdout | Fits legacy apps that only write files; isolates pipeline per Pod | Increases CPU/RAM/IO, volume management, and risk of duplicate data |
| **Direct push from application** | Appender/SDK sends logs to backend/collector over the network | Controls protocol and certain metadata directly in the app | App depends on network/collector, retry/backpressure, hard to unify across libraries |

### 10.1. Node-level Agent

This is the standard architecture when applications already write to stdout/stderr:

```text
Node A                                   Node B
  Pod orders                               Pod payments
      |                                        |
  CRI log files                           CRI log files
      |                                        |
  Logging agent (DaemonSet)              Logging agent (DaemonSet)
      |                                        |
      +------------------+---------------------+
                         |
                         v
                   Central backend
```

The agent can be Fluent Bit, Vector, or OpenTelemetry Collector with an appropriate receiver. It reads files on the node, parses the container format, enriches metadata such as namespace/pod/container, and forwards events to the backend.

**Permissions note:** agents typically need to mount the host log path into the Pod with read access. Do not grant `privileged: true` or cluster-wide permissions if the agent does not need them. Design RBAC, hostPath mounts, network policies, and secret access following least privilege.

### 10.2. Sidecar

A sidecar is useful when an application cannot be changed away from file logging or has specialized log sources. A sidecar can tail a shared file and print to its own stdout to leverage an existing node-level pipeline.

However, reading a file and re-printing to stdout can **double local storage usage** (the original file plus the sidecar's CRI log). If the node agent reads both the original file and the sidecar's stdout, the central store may also receive **two copies of the same event**.

Do not add a sidecar just to log to stdout in a Java application that already has a ConsoleAppender.

### 10.3. Direct Push

An application can use a Log4j2 SocketAppender, an HTTP/OTLP exporter, or another tool to push logs directly. You must define policies for timeouts, TLS, retries, buffering, and behavior when the collector is unavailable.

**Do not assume TCP or TLS means logs are durably stored.** A successful socket write is not an acknowledgment that the backend has indexed and persisted the event. If zero log loss is required, design dedicated durability and acknowledgment mechanisms rather than relying solely on logger calls.

## 11. OpenTelemetry Collector and the `filelog` Receiver

**OpenTelemetry Collector** is one option for node-level collection. With a distribution that includes the **`filelog` receiver** (such as Collector Contrib or a corresponding Kubernetes build), the agent can tail container log files and send them through a pipeline of receivers, processors, and exporters.

A conceptual receiver example:

```yaml
receivers:
  filelog:
    include:
      - /var/log/pods/*/*/*.log
    include_file_path: true
    operators:
      - id: container-parser
        type: container
```

This is **only a snippet**, not a complete Collector configuration: it omits `service.pipelines.logs`, processors, exporters, credentials, hostPath mounts, and RBAC. The receiver must have permission to read the actual paths on the node, and the Collector version/distribution must support the `type: container` operator.

The container parser operator is designed to handle the corresponding container log file format and extract useful stream/metadata fields. After parsing the outer CRI format, the pipeline may also need to parse the application's JSON payload to promote `event`/`order_id` into first-class fields.

### Helm Preset Example

The OpenTelemetry Collector Helm chart provides a preset option:

```yaml
mode: daemonset

presets:
  logsCollection:
    enabled: true
```

This is **an illustrative `values.yaml` snippet**, not a full production deployment configuration. You must select an image/distribution that includes the `filelog` receiver, configure an **exporter to a real backend**, set up authentication/TLS, resource limits, and verify the current chart documentation.

A critical point: if the collector scrapes **the collector's own stdout** while a debug exporter prints every received log back to stdout, an **explosive log loop** can form. When using presets, understand how collector self-logs are excluded and ensure ingested data cannot feed back into the same receiver.

### Agent Processing Principles

- Persist offsets/checkpoints as supported by the agent to reduce data loss or duplication on restarts.
- Handle rotation: deleted or truncated files require explicit handling policies.
- Bound memory/queues and configure retries when the backend is slow.
- Distinguish parse errors from transport errors; create metrics and alerts for both.
- Do not assume exactly-once delivery: retrying after a timeout can cause duplicates even when trying to avoid loss.
- Control labels and cardinality so per-request IDs do not create unbounded series or index explosion.

## 12. Structured Logging: One Event per Line

To make parsing easy for collectors, single-line JSON logs (**JSON Lines/NDJSON**) are often a strong choice when supported by your infrastructure:

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"orders","event":"order_processed","order_id":"ORD-101","outcome":"SUCCESS","correlation_id":"req-7a"}
```

This is an **illustrative JSON example**, not a guarantee that every Java logger produces the exact same structure.

Keep fields consistent:

| Field | Meaning | Recommendation |
| --- | --- | --- |
| `timestamp` | Event time at the application or collection layer | Format with timezone, typically UTC |
| `level` | Log level | `INFO`, `WARN`, `ERROR`… per framework |
| `service` | Application identity | Stable name; do not embed request IDs |
| `event` | Event type | `order_processed`, `payment_retry` |
| `order_id` | Business ID useful for investigation | Do not use as an indexed label with high cardinality unless necessary |
| `outcome` | Result | Controlled set of values |
| `reason_code` | Reason code | Stable set of codes, not free-form error sentences |
| `correlation_id` / `trace_id` | Links logs across a request/trace | Propagated across appropriate boundaries |
| `exception` | Error/stack trace details | Encoded into JSON by the encoder so lines do not break |

In **real Java logging**, never build JSON by string concatenation with user data; use an encoder/layout that properly handles double quotes, backslashes, newlines, and data types. The Section 4 example only prints **pre-validated JSON constants** to demonstrate streams.

A JSON encoder can represent a stack trace as **a single JSON string with escaped newline characters**, keeping one LogEvent on one NDJSON line. If a text formatter emits multi-line stack traces, the collector needs **multiline aggregation** with clear rules; otherwise, a single exception can be split into dozens of separate events.

## 13. Log4j2 and Logback for Java Containers

### 13.1. Log4j2 ConsoleAppender

In Log4j2, `ConsoleAppender` allows targeting `SYSTEM_OUT`. A configuration using **JSON Template Layout**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <JsonTemplateLayout/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

This is a **structurally complete `log4j2.xml`**, but running it requires `log4j-api`, `log4j-core`, and a compatible version of the **`log4j-layout-template-json`** dependency. The layout determines the JSON schema; `target="SYSTEM_OUT"` determines the stream. **Do not assume the output uses the exact same field names as the Section 12 JSON example** without checking the template/encoder.

A simpler text configuration requires only `PatternLayout` and Core:

```xml
<Console name="CONSOLE" target="SYSTEM_OUT">
    <PatternLayout charset="UTF-8"
        pattern="%d{ISO8601} %-5p %c - %enc{%m}{CRLF}%n"/>
</Console>
```

This is an **Appender snippet**, not a standalone XML file; place it inside `<Appenders>` and reference it in a logger/root. `%enc{%m}{CRLF}` escapes CR/LF characters in the message to help mitigate log injection via the message; it does not automatically mask secrets or sanitize data from all other converters.

### 13.2. Logback ConsoleAppender

For SLF4J applications using Logback, `logback.xml` can contain:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is a **structurally complete Logback file**, but it only takes effect if the application uses compatible Logback/SLF4J versions. This text pattern does not automatically turn each line into JSON. If you need real JSON, use a compatible JSON encoder and configure its schema.

### 13.3. SLF4J API vs. Provider

If code calls `org.slf4j.Logger.info(...)`, the SLF4J API itself does not decide between stdout and stderr. The provider/backend does.

For example, `slf4j-simple` writes to stderr by default, but can be configured with:

```properties
org.slf4j.simpleLogger.logFile=System.out
```

in the runtime's `simplelogger.properties`. This setting is for **SimpleLogger** and does not change the target of Logback or Log4j2.

A common mistake is adding multiple providers/adapters at once, leading to warnings or duplicate logging. Before tuning container logging, identify the actual backend selected by your framework (for example, via a starter dependency).

## 14. Application Timestamps vs. Runtime Timestamps

An application JSON line may include a `"timestamp"` added by the logger/encoder. Docker `json-file` or CRI also records an outer timestamp. When the collector parses the record, you may have **two timestamps**:

1. **Event timestamp**: when the application created the event.
2. **Observed/ingest timestamp**: when the runtime/agent/backend received or wrote the event.

They do not necessarily match due to buffering, scheduling, network delays, retries, and differing host clocks.

When investigating a distributed workflow:

- Use timestamps with explicit timezones, preferring UTC ISO 8601.
- Know which field the dashboard sorts by; switching from ingestion time to event time may reveal "late-arriving" events.
- Do not infer absolute ordering across two containers solely from timestamps if clocks are not tightly synchronized.
- Use `trace_id`, `span_id`, and `correlation_id` to correlate requests rather than relying on time alone.
- Verify that the runtime wrapper's timestamp does not overwrite the application's timestamp; preserve the meaning of each field.

Do not include current wall-clock time in constant output for learning examples if the goal is **deterministic stdout**, because the output will change on every run. The Java example in Section 4 intentionally omits dynamic timestamps.

## 15. Kubernetes Metadata: Pod, Node, Namespace, Container

To query logs across multiple replicas, a message like `"request failed"` is not enough. Collectors typically enrich events with **resource metadata** such as:

```text
service.name       = orders
k8s.namespace.name = shop
k8s.pod.name       = orders-5bf...
k8s.container.name = app
k8s.node.name      = worker-02
deployment.environment = staging
```

This is an **illustration of field names in a system using semantic conventions**, not fields that Kubernetes automatically prints into every stdout message.

Enrich metadata at the appropriate layer:

- The application knows **event, outcome, order_id, correlation_id**.
- Kubernetes/agent knows **namespace, pod, container, node**, and can attach labels from the metadata API.
- The deployment platform knows **environment, version, cluster, region**.
- The backend decides how fields are indexed, cardinality limits, and query permissions.

Do not blindly copy every environment variable and Pod label into logs. Some values may contain secrets or create uncontrolled label cardinality. Select useful metadata and enforce policies for secrets and high-cardinality IDs.

## 16. Multiline Stack Traces and CRI Partial Logs

A traditional Java exception can span multiple lines:

```text
ERROR event=order_save_failed
java.io.IOException: connection timeout
    at example.orders.Repository.save(Repository.java:42)
    at example.orders.OrderService.create(OrderService.java:18)
Caused by: java.net.SocketTimeoutException: Read timed out
    at example.net.Client.call(Client.java:25)
```

This is an **illustrative log**. If the collector treats every newline as a separate event, a single error becomes multiple records, skewing dashboard counts and breaking stack trace correlation.

There are two main options:

**A. JSON one-event-per-line:** the encoder serializes the stack trace into a single string field; newlines inside the JSON string are escaped, so NDJSON parsers still treat it as one event. This is usually the most reliable approach for structured pipelines.

**B. Multiline aggregation at the collector:** use rules to detect start lines, stack frames, `Caused by`, and enforce line/time limits. These rules must be tested against the actual output formats of your libraries and versions.

Alongside **application** multiline output, the CRI runtime also has **`P` (partial)** and **`F` (full)** flags when splitting records at the container layer. These are two different concerns, and sometimes both must be handled:

- Reassemble CRI fragments into the full record content before parsing the payload.
- If the application payload still contains a multi-line stack trace, a subsequent multiline parser may be needed.

Do not merge lines with an unbounded generic regex without size or timeout limits: malformed data can cause the collector to buffer indefinitely, consume excessive RAM, or merge two unrelated events.

## 17. Log Loss, Duplication, and Troubleshooting

A log pipeline can fail at several points:

| Symptom | Where to Check | Action |
| --- | --- | --- |
| App is running but no new logs appear | Level/Filter, backend, stdout/stderr | Verify logger/provider and console configuration |
| `docker logs` is empty | `none` driver, runtime config, or process hasn't written yet | Check driver/container and run command |
| `kubectl logs` shows logs but dashboard does not | Agent/collector/backend | Check filelog tailing, parser, exporter, auth, network |
| Dashboard has logs but lacks `order_id` | JSON payload not parsed, wrong schema | Parse runtime layer then payload; check field names |
| Logs lost after restart/node failure | Rotation/local retention, agent lagged | Improve centralized collection and buffer durability if needed |
| Logs appear twice | Console + file both collected; multiple agents on node; retries | Designate a canonical source; track IDs/deduplication |
| Logs arrive very slowly | Backpressure, queue, network, or slow backend | Monitor queues, retries, and ingestion latency |
| Stack traces split into multiple events | Broken CRI partial handling or multiline parser | Use container parser and multiline policy |
| Explosive log growth at collector | Agent is scraping its own debug output | Exclude collector source or change exporter |
| Node log files fill the disk | Misconfigured rotation/retention or excessive log rate | Configure kubelet/Docker rotation; reduce noisy logs |
| Logs exist but lack pod/namespace | Broken metadata enrichment or missing RBAC | Check file path patterns, parser, API permissions |
| Sensitive data exposed in logs | App logs secrets, misconfigured collector RBAC | Minimize data, redact, enforce secret policy and RBAC |

### Layer-by-Layer Troubleshooting Workflow

1. **At the application:** verify the right logger, level, stdout/stderr target, and clear `event` codes.
2. **At the container runtime:** do `docker logs` or `kubectl logs` show the event? If not, locate where the appender or runtime driver is misconfigured.
3. **At the node/agent:** can the agent read the log files; are offsets, rotation, permissions, and parsers working?
4. **At the collector:** is it receiving events, parsing CRI + payload, enriching metadata, and forwarding?
5. **At the backend:** are there authentication errors, quota limits, rate limits, transform pipeline errors, or retention drops?
6. **At the dashboard:** is the query using the right timestamp field, namespace, service, level, and environment?

Do not keep raising log levels or adding `println` statements when an event is already visible in `kubectl logs` but missing from the dashboard; at that point, investigate **downstream of the runtime** rather than adding more application logs.

## 18. Security and Privacy of Container Logs

A container may run in an internal namespace, yet its logs are often aggregated into a system accessed by multiple teams. Security must therefore be designed from **emitted content** to **storage destination**.

Core principles:

1. **Never log secrets:** passwords, tokens, session cookies, API keys, OTPs, private keys, full card numbers, and sensitive payloads.
2. **Limit PII:** user/order identifiers may require encryption, masking, or safe surrogate IDs depending on policy; not every ID is benign.
3. **Use safe encoders:** messages can contain newlines, quotes, or control characters, causing log injection if unescaped.
4. **Do not capture all environment variables:** environment variables can hold secrets; metadata enrichment must select allowed fields only.
5. **Restrict agent permissions:** grant hostPath, service accounts, RBAC, and network egress strictly as needed.
6. **Protect data in transit:** use TLS, exporter/collector authentication, and certificate management; avoid sending unencrypted logs over untrusted networks.
7. **Enforce backend access control:** querying and exporting should require role-based access, access auditing, and policy-driven retention.
8. **Limit volume:** excessive log volume increases both cost and the storage surface area for sensitive data.
9. **Audit where logs are replicated:** CI logs, local Docker files, node agent buffers, collector staging, backups, and archives.
10. **Do not treat logs as the sole audit system:** auditing requires integrity guarantees, verifiability, and dedicated business design.

JSON logging reduces parsing errors, but **valid JSON does not automatically secure data**. TLS protects data in transit, yet the collector still decrypts and processes the contents; never emit secrets just because HTTPS is enabled.

## 19. Controlling Volume, Performance, and Cost

High-throughput services can emit hundreds of thousands of events per minute. Not only the application, but also the runtime, agent, collector, and backend bear the cost.

A strategy should consider all of these together:

- **Log level:** `INFO` for operationally valuable events; `DEBUG`/`TRACE` for time-bounded and scope-bounded investigations.
- **Event count:** avoid logging the same exception at controller, service, and repository layers as three separate incidents.
- **Payload size:** avoid dumping entire requests/responses or objects with huge `toString()` outputs.
- **Sampling:** can reduce low-priority logs, but must not be applied indiscriminately to mandatory events.
- **Buffers/queues:** bound and monitor them; know whether full queues block, drop, or retry.
- **Rotation:** prevents filling node disks, but can truncate history if the agent reads too slowly.
- **Backpressure:** a stalled stdout/pipe or exporter can affect the logging process.
- **Cardinality:** do not turn `request_id` or `order_id` into unbounded indexed labels across all systems.
- **Retention:** `TRACE` logs do not need to be kept for years; base policies on business needs.
- **Data durability:** if an event must never be lost, build a durable source such as a database, audit store, or transactional outbox outside observability logging.

Useful operational metrics include input events/bytes, processed events, dropped records, parse errors, exporter retries, queue size, backend ingest lag, and node disk usage. Do not rely solely on line counts in `kubectl logs` to assert pipeline integrity.

## 20. Self-Check Questions

1. **Where do container logs start?** Typically from the application logger through a Console Appender to stdout/stderr.
2. **Is `docker logs` a centralized log store?** No. It reads data still held by the runtime/driver.
3. **Which default driver does Docker Engine commonly use?** `json-file` unless changed; always check the live daemon.
4. **Does the `json-file` driver automatically parse JSON inside `log` into `event` and `order_id`?** No. The JSON wrapper has a `log` field containing the payload, which the collector may need to parse further.
5. **Why should rotation be configured?** To prevent local log files from filling the disk; it does not mean permanent log storage.
6. **Does Docker non-blocking guarantee zero dropped logs?** No. A full buffer can drop records.
7. **In Kubernetes, where does kubelet typically direct the runtime to write logs on Linux nodes?** Under `/var/log/pods`.
8. **What components are in a CRI log line?** Timestamp, stream, partial/full tag, and log content.
9. **What do `F` and `P` indicate in CRI?** Full record and partial fragment.
10. **Does `kubectl logs` return all old rotated files?** No; typically only the current latest file.
11. **Does `kubectl logs --previous` show every historical restart?** No. Only the previous instance if still retained by kubelet.
12. **Why is a DaemonSet commonly used for node-level log agents?** To run an agent that reads log files on every node.
13. **When should a sidecar be used?** When an app cannot write directly to stdout or needs a Pod-specific log pipeline; weigh overhead and duplication risks.
14. **Does a JSON event on stdout automatically become structured JSON in the backend?** No; the collector must parse the payload and preserve the schema.
15. **Why shouldn't multi-line Java stack traces be logged without a multiline parser?** A single exception can be split into multiple false events.
16. **What do two timestamps in a log mean?** One can be when the application emitted the event, and the other when the runtime/collector received it.
17. **Why can a collector create a log loop?** It scrapes its own stdout and exports debug output back to stdout, creating repeated ingestion.
18. **Should stdout logs be relied on as proof that a transaction committed?** No. Logging is for observability and does not replace durable state stores.
19. **If `kubectl logs` has an event but the dashboard does not, where should you check?** The agent, parser, exporter, backend, and query before modifying Java code.
20. **If a Pod is deleted, are its logs guaranteed to remain viewable?** No. A cluster-level system must have collected and stored them independently of the Pod/node.

## 21. References

- Kubernetes, Logging Architecture: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes, Observability: https://kubernetes.io/docs/concepts/cluster-administration/observability/
- Docker Engine, Configure logging drivers: https://docs.docker.com/engine/logging/configure/
- Docker Engine, JSON File logging driver: https://docs.docker.com/engine/logging/drivers/json-file/
- Docker Engine, Local file logging driver: https://docs.docker.com/engine/logging/drivers/local/
- OpenTelemetry, Collector Helm chart and logs collection preset: https://opentelemetry.io/docs/platforms/kubernetes/helm/collector/
- OpenTelemetry, Container log parser: https://opentelemetry.io/blog/2024/otel-collector-container-log-parser/

These references may change across Docker, Kubernetes, runtime, and collector versions. When deploying in production, verify compatible settings against your target environment rather than treating illustrative values as universal cluster defaults.

**Key takeaway:** **Java app emits logs → container runtime captures stdout/stderr → kubelet/driver holds short-term logs → agent/collector parses and forwards → backend stores and indexes**. Choose a structured format, preserve event boundaries and metadata, understand rotation/buffering/multiline behavior, monitor for loss or duplication, and separate **system observability** from **mandatory durable business data**.
