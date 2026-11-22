# Rotation in Containers: Managing Java Logs on Docker and Kubernetes

## 1. What is rotation in containers?

**Log rotation** is the process of bounding, rotating, or replacing growing log files or segments, usually accompanied by a policy for retaining and deleting old data. In a Java application running as a **container**, a more important question than "which rolling file library should I choose?" is: **who owns the log output and who actually performs rotation?**

There are two main architectures:

- **Application writes to stdout/stderr:** Logback, Log4j 2, or JUL forwards events to the console. Docker/the container runtime and, if present, kubelet manage the container log files on the node. Rotation typically lives **outside the JVM**.
- **Application writes to files:** Logback `RollingFileAppender` or Log4j 2 `RollingFile` manages files inside the container filesystem or on a volume. Rotation can live **inside the application**; the runtime only manages stdout/stderr automatically, not every business log file created by Java.

A container can still write to both the console and a file, but if both paths capture the same event, you must distinguish **intentional fan-out** from accidental duplication.

Example:

```text
Java Application
   |
   +-- ConsoleAppender --> stdout/stderr
   |                         |
   |                         v
   |                   Container runtime
   |                         |
   |                         v
   |                   Node log segments
   |                         |
   |                Runtime/kubelet rotation
   |                         |
   |                         v
   |                   Collector -> log store
   |
   +-- RollingFileAppender --> /app/logs/app.log
                                 |
                                 v
                          In-JVM rotation
                                 |
                                 v
                          Filesystem/volume
                                 |
                                 v
                          Collector reads file (if any)
```

**Key takeaway:** Docker's log size limit does not automatically bound `/app/logs/app.log` written by `RollingFileAppender`. Conversely, enabling a rolling policy for Logback does not automatically configure the size of stdout log files managed by Docker or kubelet.

## 2. Why do containers need rotation?

Containers are redeployed, scaled across replicas, and run on nodes with finite disk capacity. Unbounded logs can:

1. Fill up the node's filesystem/ephemeral storage or a volume.
2. Cause I/O pressure, slowing down the runtime and other processes.
3. Cause pods to suffer from disk pressure warnings, eviction, or write failures.
4. Generate massive data volumes for collectors, the network, and centralized storage.
5. Multiply storage costs and obscure investigations when retries or exceptions occur continuously.
6. Retain secrets or personal data longer than policy allows.
7. Make log viewing, searching, and stack trace retention hard to operate.

Rotation bounds the **local logs that can be retained**; it is not the sole solution. If log volume increases tenfold, you also need to review log levels, sampling, duplicate records, stack trace volume, collector throughput, and operational metrics.

### Three easily confused concepts

| Concept | What question does it answer? | Example |
| --- | --- | --- |
| **Rotation** | When to switch away from the active segment/file? | When the file reaches about 10 MiB. |
| **Retention** | How many files / how long to keep before deleting? | Keep at most three local files. |
| **Shipping/collection** | How are logs sent to and stored in another system? | An agent reads node logs and ships them to a central store. |

Having rotation **does not mean** a durable copy exists in a centralized logging system. Having a collector also **does not guarantee** every record will be shipped before the local file is rotated and deleted.

## 3. Default principle: prefer stdout/stderr for typical container applications

For many Java services running in Docker/Kubernetes, the easiest architecture to manage is:

```text
SLF4J/Log4j 2 API
      |
      v
Logback/Log4j 2 ConsoleAppender
      |
      v
stdout/stderr
      |
      v
container runtime / kubelet
      |
      v
node log files + rotation
      |
      v
node-level collector
      |
      v
central log storage
```

Advantages of **writing to the console**:

- No need to manage log directory locations inside the image.
- No need to configure a writable volume just to hold text logs.
- Logging aligns consistently with the container lifecycle.
- The runtime and platform provide access mechanisms such as `docker logs` or `kubectl logs`.
- A node-level collector can read logs from many workloads in the same way.
- Responsibility for rotation, retention, alerting, and access control is easy to centralize at the operations layer.

However, **stdout does not mean data is kept forever**. A deleted container, a failed node, rotated/deleted log files, or a lagging collector can all cause the loss of logs that only existed locally. For audit events or business data that require guarantees, you must design a storage/delivery mechanism with appropriate reliability rather than relying solely on the console.

### Choosing stdout or stderr?

There is no Java rule requiring `ERROR` to be written to `stderr`. Logback `ConsoleAppender` can be configured with `System.out` or `System.err`; Log4j 2 has `SYSTEM_OUT` and `SYSTEM_ERR`. Many applications write all logs containing a `level` field to stdout; some separate stderr for errors. You should **choose an explicit contract and test it**, rather than assuming the level name determines the stream.

When using Kubernetes, both container stdout and stderr can be recorded by the runtime with stream metadata. If a viewer interleaves both streams, the ordering between records is not necessarily strictly preserved.

## 4. Where does Docker store console logs and who performs rotation?

When an application writes to stdout/stderr, Docker Engine forwards the data to the **logging driver** configured for the container. Common drivers include `json-file`, `local`, `journald`, or external destinations depending on the system. **The exact rotation mechanism depends on the driver in use**, not a single uniform policy applied identically to every driver.

With the **`json-file`** driver, Docker stores records in an internal format with timestamp and stream metadata. Configuring `max-size` and `max-file` can limit local disk usage and file count.

Example:

```bash
docker run --name java-log-demo \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  my-java-image
```

This is an **illustrative command**; the `my-java-image` image must exist before running. Key parameters:

- `--log-driver json-file`: selects the driver for this container.
- `--log-opt max-size=10m`: limits each log file to roughly 10 MB according to driver syntax.
- `--log-opt max-file=3`: limits the number of files kept according to how the driver handles rotation.
- `--name`: assigns a name for easier `docker logs` and `docker inspect`.

**Do not assume every Docker Engine has rotation enabled by default.** The `json-file` driver can grow unbounded if `max-size` is not set, depending on the daemon configuration and environment. In addition, `max-file` only takes effect for rotation when paired with the corresponding size option for that driver.

### Docker logging driver and collector are two separate layers

`docker logs` is primarily an interface for **reading records provided by supported drivers**, not a place to configure retention. A collector can ship local logs to a centralized system, but collector failure does not necessarily prevent rotation from deleting old files.

Docker keeping at most a few files on the host does not guarantee that a container's full log history will still be viewable a week later. To retain logs longer, you must configure a central store and its retention policy.

### The `local` driver and other drivers

Docker also has a `local` driver aimed at more efficient local log management in many environments, with its own rotation options. However, not every driver has the same option names, the same `docker logs` behavior, or the same log-reading mechanism.

**How to verify:** inspect the actual driver and options on the container; then consult the documentation for that exact driver and Docker version. Do not apply `json-file` policies to a driver that streams logs directly over the network without verifying.

## 5. Docker Compose: configuring rotation for a Java service

In `compose.yaml`, you can set the driver and options at the **service** level:

```yaml
services:
  app:
    build: .
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "3"
```

**Note:** values such as `"1m"` and `"3"` are **strings**, matching the logging driver option types. These settings limit stdout/stderr logs **managed by Docker** for the service's container; they do not automatically affect other files inside the filesystem.

With Compose running, identify the container ID and inspect it:

```bash
docker compose ps -a -q app
docker compose logs --tail=20 app
```

If you want to view the actual logging configuration after obtaining the container ID:

```bash
docker inspect --format '{{json .HostConfig.LogConfig}}' <container-id>
```

In the command above, `<container-id>` is a **real value** that must be replaced with the ID from `docker compose ps -a -q app`; this is an **illustrative inspection command**, not literal text to run verbatim.

The inspect output should show the `json-file` driver along with the desired size and file-count options. **Having the right configuration does not mean rotation has actually occurred**: to verify behavior, you must emit enough logs to exceed the threshold and observe old data being retained/deleted according to policy.

### Docker daemon-wide default configuration

When you have administrative access to Docker Engine, a default policy can be set in the daemon configuration, for example:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

This is **illustrative daemon configuration content**, not JSON read by the Java application. The file location and how to reload/restart the daemon depend on the operating system and Docker installation method. Changing the default **does not automatically apply retroactively to all existing containers**; you normally need to recreate containers with the desired configuration.

Do not arbitrarily restart the Docker daemon on a production host, as it can affect workloads. Apply configuration changes through your infrastructure workflow, with testing and maintenance windows as needed.

## 6. Runnable Java 17 example: generating verifiable console logs

This example uses **pure JDK 17**, with no external logging libraries outside the JDK, to cleanly separate **emitting bytes to stdout/stderr** from **Docker-managed rotation**.

In a production application, you should use a logging facade/backend with structured fields and log levels rather than scattering `System.out.println` across services. This lesson intentionally uses standard streams so that routing is **independent** of any specific backend.

### 6.1. `ContainerLogDemo.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ContainerLogDemo {
    private ContainerLogDemo() {
    }

    public static void main(String[] args) {
        int count = args.length == 0 ? 6 : Integer.parseInt(args[0]);

        if (count < 1) {
            throw new IllegalArgumentException("count must be positive");
        }

        PrintStream out =
                new PrintStream(System.out, true, StandardCharsets.UTF_8);
        PrintStream err =
                new PrintStream(System.err, true, StandardCharsets.UTF_8);

        for (int i = 1; i <= count; i++) {
            out.println("INFO|event=order.created|seq=" + i
                    + "|order=O-" + i);

            if (i % 3 == 0) {
                err.println("ERROR|event=gateway.failed|seq=" + i
                        + "|code=UPSTREAM_TIMEOUT");
            }
        }
        out.flush();
        err.flush();
    }
}
```

Properties:

1. By default, generates **6 INFO events** and **2 ERROR events**, with deterministic `seq` values.
2. INFO goes to `stdout`; ERROR goes to `stderr` as chosen by the Java code itself.
3. `PrintStream(..., UTF_8)` encodes data as UTF-8; the buffer has auto-flush enabled.
4. No timestamps or thread names are fixed, making the output easy to test.
5. If a positive integer is passed as an argument, the program runs that exact number of iterations; useful in log load-testing environments.
6. The example **does not rotate files itself** and **does not delete logs itself**. It simply writes to streams for the runtime to handle.

Compile and run on a machine with JDK 17:

```bash
javac -encoding UTF-8 ContainerLogDemo.java
java ContainerLogDemo >stdout.log 2>stderr.log
```

After the commands above, the **exact contents of `stdout.log`** with no arguments are:

```text
INFO|event=order.created|seq=1|order=O-1
INFO|event=order.created|seq=2|order=O-2
INFO|event=order.created|seq=3|order=O-3
INFO|event=order.created|seq=4|order=O-4
INFO|event=order.created|seq=5|order=O-5
INFO|event=order.created|seq=6|order=O-6
```

**Exact contents of `stderr.log`:**

```text
ERROR|event=gateway.failed|seq=3|code=UPSTREAM_TIMEOUT
ERROR|event=gateway.failed|seq=6|code=UPSTREAM_TIMEOUT
```

Lines are written separately per stream; when displayed together in a single terminal, **you should not assert a strict interleaved order** between stdout and stderr.

### 6.2. `Dockerfile`

Use a multi-stage build so only the class file and JRE are included in the runtime image:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /src
COPY ContainerLogDemo.java .
RUN javac -encoding UTF-8 ContainerLogDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/ContainerLogDemo.class .
USER 10001
ENTRYPOINT ["java", "ContainerLogDemo"]
CMD ["6"]
```

Explanation:

- The `build` stage has JDK 17 for compilation.
- The runtime stage only contains the JRE needed to run.
- The Java process writes to **stdout/stderr**, not directly to a `/var/log/app.log` file.
- `USER 10001` runs as a non-root user inside the container; the example requires no file write permissions.
- `CMD ["6"]` provides the default argument; you can override the iteration count when running the container.
- The `eclipse-temurin` image is an example; Docker and registry access are required to build.

Build the image:

```bash
docker build -t java-rotation-lab:1 .
```

Run a container without auto-removal so you can inspect its configuration and recent history:

```bash
docker run --name java-rotation-lab \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  java-rotation-lab:1 6
```

View logs:

```bash
docker logs --tail 20 java-rotation-lab
```

`docker logs` displays records supported by the driver; stdout and stderr may appear together in a single view. **Do not treat the interleaved order of the two streams as fixed expected stdout.** If you need to know exactly which stream received data, test the two streams independently via `stdout.log` and `stderr.log` or use a tool with stream metadata.

Inspect the container's logging configuration:

```bash
docker inspect --format '{{json .HostConfig.LogConfig}}' java-rotation-lab
```

The configuration should show type `json-file` and options `max-size=1m`, `max-file=3` (JSON key ordering may vary). A single run with 6 iterations produces **too little data to trigger rotation**, so this test proves **log routing and configuration**, not that files have rotated yet.

Clean up the test container after inspection:

```bash
docker rm java-rotation-lab
```

### 6.3. Generating enough logs to test rotation

You can run a separate test container with a large iteration count, but only in an authorized environment with known disk/load capacity:

```bash
docker run --name java-rotation-load \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  java-rotation-lab:1 30000
```

This command generates 30,000 INFO and 10,000 ERROR lines across the two streams; total bytes will significantly exceed 1 MB under typical logging configurations. **Do not print all data to the terminal when checking**; view only the most recent lines:

```bash
docker logs --tail 20 java-rotation-load
docker inspect --format '{{json .HostConfig.LogConfig}}' java-rotation-load
```

Expectations to verify:

- Writing does not fail merely because logs exceed a single file.
- The log driver limits are in effect.
- Local disk usage is bounded according to policy after rotation runs.
- Recent events remain readable within the driver's capabilities.
- **Do not expect to read back all 40,000 old lines**: rotation and retention may have already purged older segments.

Verifying the actual file count and size on the host requires administrator tools/privileges and must follow runtime rules. **Do not manually edit, delete, or truncate Docker's internal log files in the engine data directory**; direct manipulation outside the driver can break file management and cause inconsistent data/log reads.

Clean up the container:

```bash
docker rm java-rotation-load
```

Note that `docker rm` can only remove stopped containers. The Java example exits normally, so the container transitions to the exited state.

### 6.4. Distinguishing runnable examples from system procedures

The Java file runs standalone with JDK 17, producing deterministic output per stream. The Docker examples require Docker Engine, container execution permissions, and images from a registry. `docker inspect` output and segment locations depend on the environment; therefore, this lesson **does not fabricate byte counts, inodes, or absolute node log file paths**.

## 7. Applying Docker Compose to the Java program just created

Once you have `Dockerfile` and `ContainerLogDemo.java`, place `compose.yaml` in the same directory:

```yaml
services:
  app:
    build: .
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "3"
    command: ["6"]
```

In the sample image, `ENTRYPOINT ["java", "ContainerLogDemo"]` receives `CMD ["6"]`; Compose's `command: ["6"]` plays the same role of passing the iteration count argument.

Run and view logs:

```bash
docker compose up -d --build
docker compose logs --tail=20 app
docker compose ps -a
docker compose down
```

With the default iteration count, no actual rotation occurs because there are too few logs. To test size limits, you can intentionally change `command` to a large number in a **test environment**, while avoiding exhausting quotas or overwhelming collectors. After editing logging options in Compose, ensure the container is **recreated** with the new configuration; changing YAML and inspecting an old container is insufficient evidence.

**Do not apply `compose.yaml` configuration to Kubernetes.** Kubernetes does not directly use Docker Compose's `logging.driver`/`logging.options` for pods. They are two different deployment layers.

## 8. Kubernetes: rotation belongs mainly to kubelet and the container runtime

On Kubernetes, Java applications typically write to stdout/stderr. The container runtime writes data in the runtime/CRI log format on the node; kubelet coordinates **container log rotation** according to node configuration and runtime capabilities.

High-level path:

```text
Java -> stdout/stderr -> container runtime
                               |
                               v
                     node container log files
                               |
                               v
                         kubelet rotation
                               |
                      +--------+---------+
                      |                  |
                      v                  v
                 kubectl logs      node log agent
                                         |
                                         v
                                   central storage
```

Some kubelet configuration properties related to rotation:

```yaml
containerLogMaxSize: "10Mi"
containerLogMaxFiles: 5
```

This is a **kubelet configuration snippet**, **not a complete Pod manifest**, and not properties you can paste into `containers:` of a Kubernetes Deployment. Meaning:

- `containerLogMaxSize`: configured maximum size for a container log file before rotation is needed.
- `containerLogMaxFiles`: maximum number of log files retained per container under kubelet policy.
- Actual behavior also depends on the Kubernetes version, runtime, and node handling mechanisms.

In managed Kubernetes clusters, changing kubelet configuration may require modifying node pools, launch templates, or provider settings and rolling out appropriate nodes. **Do not directly edit kubelet configuration on production nodes** without an infrastructure management process; changes may be overwritten by cluster management.

### Rotation is not a Pod environment variable

The following lines **do not configure kubelet rotation**:

```yaml
env:
  - name: LOG_ROTATE_MAX_SIZE
    value: "10Mi"
```

The snippet above only defines an environment variable named by the application. It does not affect kubelet unless a component actually reads that variable and acts on it. If a Java application uses `RollingFileAppender` and reads the variable itself, that is **in-application rotation**, distinct from node-level rotation of stdout/stderr.

### What scope can `kubectl logs` read?

Commonly used commands:

```bash
kubectl logs my-pod -c app --tail=100
kubectl logs my-pod -c app --since=10m
kubectl logs my-pod -c app --previous
```

The pod/container names above are **illustrative examples** and must be replaced with real names in your cluster.

- `--tail=100`: retrieves up to the last N lines per command behavior.
- `--since=10m`: limits the time window.
- `--previous`: retrieves logs from the **previous container run in the same pod**, when still retained by the runtime/kubelet.
- `--previous` **does not mean** reading "the previously rotated file".

In standard Kubernetes, `kubectl logs` is limited to data provided by kubelet from existing container logs; rotated segments should not be assumed fully accessible via this command. Some Kubernetes documentation notes that `kubectl logs` only serves the latest log file contents after rotation, not the entire history. To query older logs or across multiple restarts/nodes, you need **a collector and a central store with appropriate retention**.

### Container restart, Pod replacement, and node loss

Three different operational events:

1. **Container restart within the same pod:** the runtime may retain part of the previous run's logs; `kubectl logs --previous` can be useful.
2. **Pod deleted/replaced by a new pod:** access to the old pod's local logs diminishes or is lost due to node/runtime garbage collection.
3. **Node fails or is replaced:** data existing only on the node may be lost completely.

Therefore, rotation and `kubectl logs` serve **near-real-time debugging**, not a long-term storage strategy.

## 9. Kubernetes: a Deployment logging stdout/stderr properly

Suppose the application is packaged in image `registry.example.com/demo/java-rotation:1`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-rotation-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: java-rotation-demo
  template:
    metadata:
      labels:
        app: java-rotation-demo
    spec:
      containers:
        - name: app
          image: registry.example.com/demo/java-rotation:1
          args: ["6"]
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              memory: "256Mi"
```

This is an **illustrative structural manifest**; it cannot be deployed verbatim if the image has not been built/pushed and the cluster cannot access the registry. The application still writes only to stdout/stderr; **no volume is needed** for text logs in this approach. Rotation is configured on the node/kubelet, not in the Deployment.

After deploying with a real image, you can inspect:

```bash
kubectl get pods -l app=java-rotation-demo
kubectl logs deployment/java-rotation-demo -c app --tail=20
```

Because the sample Java program exits quickly, running it as a **Deployment** (which expects long-lived workloads) will cause kubelet to **restart the container**, potentially creating a restart loop. This is **not an appropriate production configuration for a short batch program**. For run-to-completion tasks, a Kubernetes `Job` is more suitable; the Deployment example here merely illustrates where `image`/`args` go and the separation between Pod spec and node rotation configuration.

For long-running Java services (web APIs, message consumers), the JVM process must continue serving or waiting for work; only then is a Deployment appropriate.

### Investigating rapid log growth on a cluster

If a pod emits excessive logs:

- Identify the root cause: DEBUG log level left enabled, repeated exceptions, retry loops, large message payloads, or a bug.
- Check whether the collector is keeping up.
- Check ephemeral storage and signs of disk pressure/eviction on the node.
- Check kubelet/node pool log rotation limits.
- Ensure the central logging system still has the data needed for investigation before the node deletes old files.
- Consider meaningful sampling/event throttling rather than merely increasing per-file size.

**Fix the noisy log source**, do not just increase max size. Rotation bounds the impact on local disk, but it does not cure an application writing millions of identical stack traces.

## 10. Logback in Java containers: writing to console so the runtime manages rotation

For an application using `SLF4J 2.x + Logback`, a `src/main/resources/logback.xml` configuration suited for the stdout architecture might look like:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level [%thread] %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT" />
    </root>
</configuration>
```

This is a **standalone XML configuration file**, but it only takes effect when the runtime actually uses Logback Classic as its backend and has the appropriate dependencies. The Java 17 example in section 6 **does not use Logback**, so it will not be governed by this `logback.xml`.

A log call in a Logback application might be:

```java
log.info("event=order.created order_id={}", orderId);
```

This is an **illustrative snippet** assuming a logger and `orderId` already exist in business code. Once the encoder writes the event to stdout, the container runtime decides how to store and rotate that output.

**Do not blindly configure two rotation layers for the same byte stream.** If Java only uses `ConsoleAppender`, Docker/kubelet manages the container's log file. If Java also uses `RollingFileAppender` to `/app/logs`, that is **a separate file path** requiring its own retention and collector.

### Log4j 2 equivalent in purpose

With Log4j 2 Core, a `Console` appender:

```xml
<Configuration>
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level [%t] %c - %m%n"
                charset="UTF-8" />
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="STDOUT" />
        </Root>
    </Loggers>
</Configuration>
```

This is a Log4j 2 configuration and cannot be used verbatim as `logback.xml`. Both examples intentionally **do not rotate files inside the JVM**. Rotation configuration belongs to the runtime/kubelet layer.

## 11. When an application truly needs to write files in a container

Some systems need dedicated files because:

- Legacy applications or agents only read files.
- Integration with software that has a specific file-based contract.
- Different event types need to be written with separate permissions or formats.
- Special volume/binary logs require a pipeline designed by the operations team.

In that case, you can use **Logback `RollingFileAppender`** or **Log4j 2 `RollingFile`**. But before choosing, answer:

1. Does the file live in the container's **writable layer** or on a volume?
2. Must the file survive container restarts, pod replacement, or node replacement?
3. Who deletes old files: the application, external logrotate, or an agent?
4. Which files does the collector read, and can it keep up when files are renamed/closed/opened?
5. Do multiple replicas write to **the same path**?
6. What are the disk quota, file permissions, UID/GID, and backup/retention requirements?
7. When the log directory fills up, how do the application and node react?

### Logback self-rolling file example

This is a **Logback configuration snippet**, used when compatible `logback-classic` is present:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/app/logs/application.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>/app/logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE" />
    </root>
</configuration>
```

Explanation:

- `RollingFileAppender` writes to `/app/logs/application.log`.
- `SizeAndTimeBasedRollingPolicy` uses a date-and-index `%i` filename pattern while also handling size according to configuration.
- `maxFileSize` limits the approximate file size before rollover per policy.
- `maxHistory=7` combined with a daily time pattern relates to the number of historical periods retained, not a hard guarantee of "exactly seven files".
- `totalSizeCap` adds a total historical size cap via the cleanup mechanism.
- Deletion/retention may occur during rollover/cleanup events, meaning files do not shrink immediately when an administrator edits the XML.

**Critical requirement:** `/app/logs` must exist and be writable by the Java process's UID. For images running as non-root, a mount/volume with improper permissions will prevent the file from being opened.

### Why doesn't Docker rotation handle Logback files?

The Docker logging driver by default manages data sent from container stdout/stderr. A file written directly by Java to `/app/logs/application.log` is just a **regular file** on the filesystem; Docker's `json-file` driver does not automatically detect and rotate it.

If you simultaneously have:
- Docker rotation for stdout.
- Logback RollingFile for `/app/logs`.

then those are **two log stores** with different lifecycles. You need two retention/collection rules, and duplicate logs can occur when both paths emit the same event.

## 12. Volumes, ephemeral filesystems, and Pod lifecycle

A log file residing in the container's writable layer is usually meaningful only for the container's lifecycle and should not be treated as durable storage. Some options:

| Where to write | Characteristics | Risks |
| --- | --- | --- |
| stdout/stderr | Collected by runtime/kubelet via container mechanism | Subject to rotation and GC; not retained long without a collector. |
| Container writable layer | Simple file writes, but tied to container lifecycle | Lost when container is replaced/deleted; increases storage pressure. |
| Kubernetes `emptyDir` | Shared volume for the Pod's lifecycle | Survives container restarts in the same pod, but lost when the Pod is deleted from the node. |
| PersistentVolume | Can outlive the Pod per policy/storage class | More complex write permissions, cost, concurrency, and lifecycle. |
| HostPath | Accesses a specific node's filesystem | Node affinity constraints, security/permission issues; hard to operate multi-node. |

**A volume is not a substitute for log rotation.** If you attach a PVC and write unbounded logs, the volume can still fill up. With multiple Java replicas writing to the same file on a shared volume, renames/rollovers and file locks can conflict, causing lost or interleaved logs. Usually each instance should have its own path, or you should return to the stdout + collector architecture.

### Pitfalls of running as non-root

Many production Java images use a non-root `USER`. If a volume is mounted with incompatible owner/permissions, `RollingFileAppender` cannot create the file. You should not "quick-fix" with `chmod 777` everywhere; instead use appropriate UID/GID permissions, operational groups, security contexts, or controlled provisioning mechanisms.

### Open files and rename operations

On Unix-like operating systems, a process holding a file descriptor can continue writing to the **old inode** even after the file is renamed externally. Therefore, using an external rotation tool to rename a file without instructing the logger to reopen it can send data to the wrong place. `copytruncate` can also cause lost or duplicate logs during the copy/truncate window under concurrent writes.

**Do not run Logback `RollingFileAppender` and an external logrotate on the same file without clearly designing rotation ownership.** Choose one primary mechanism and test writing during rollover.

## 13. Sidecars and collectors: how does rotation relate?

One way to collect file logs is an agent/sidecar reading files from a shared volume; another is a node-level agent reading stdout/stderr logs created by the runtime.

```text
Option A (usually simpler):
Java stdout -> runtime log -> node agent -> central storage

Option B (application requires files):
Java RollingFile -> shared volume -> sidecar/agent -> central storage
```

In Option B, you need to verify:

- The agent tracks both old and new files when rotation occurs.
- The agent recognizes offsets/inodes/rotations, neither re-reading every file from the start nor dropping the tail.
- Files being compressed/deleted before the agent finishes reading can cause log loss.
- Limits on file count, file size, backpressure, and read permissions are accounted for.
- If Java restarts, the agent handles continued writes or new files properly.
- When a pod is deleted, unshipped logs may be lost along with the ephemeral volume.

In Option A, the runtime and kubelet rotate node logs; the node agent must be compatible with the CRI/container log mechanism and the node's rotation timing. **Rotation outpacing collection** is a common source of data loss in both options.

### Why can a sidecar tailing stdout directly be problematic?

If an application already writes to stdout, there is no need to force it to write to a file and run a `tail -f` sidecar just to reprint to stdout, unless there is a proven specific requirement. This adds another buffer/stream layer, consumes extra resources, and risks duplicate or lost logs when the tail process lags, restarts, or files rotate.

## 14. JSON logging, multiline, and single-event size

When Logback/Log4j 2 writes plain text, a single stack trace can span dozens of physical lines. The Docker/Kubernetes runtime still receives bytes from stdout/stderr; the collector may store by line or chunk, sometimes having to reassemble parts from the CRI/driver.

With structured logging, an application can emit **one JSON object per line**:

```json
{"level":"ERROR","event_code":"payment.failed","request_id":"req-7","message":"Gateway timeout"}
```

This is only a **schema example**, not automatic output from Java `System.out` or Logback `PatternLayout`.

A reliable JSON encoder must escape newlines inside string values, double quotes, and control characters. Hand-assembling text like `{"message":"%msg"}` easily produces invalid JSON if the message contains special characters.

### Rotation and large single-line logs

If a single JSON event is very large (e.g., a multi-MB payload), it can:

1. Exceed the record/line size limit of the collector or storage service.
2. Be split by the runtime into multiple segments/partial records depending on the specific mechanism.
3. Increase the risk of data loss if the collector fails to reassemble them properly.
4. Increase storage and query costs.
5. Cause rotation to happen very rapidly even at low event rates.

Do not log entire requests/responses or large objects for "easy debugging". Log event codes, correlation IDs, sizes, error codes, and permitted data. When large payloads are truly needed, use a dedicated, controlled storage system.

### One log line is not one transaction

A single request can generate multiple events and stack traces. Therefore, do not use the line count in rotated files as a **transaction count** or **error rate**. To measure transaction failures, use metrics/counters or a well-defined request-completion event with appropriate durability guarantees.

## 15. Retention policy: max-size and max-files are not enough for every goal

A configuration like `max-size=10m` and `max-file=3` is usually meant to bound **local data** kept under the driver, not to guarantee three days of data retention.

Why?

- A high-volume application can rotate through all three files in just a few minutes.
- A low-volume application might keep a single file for many days.
- Rotated data is still subject to the container/node lifecycle.
- The collector may lose connectivity while old logs are being deleted.
- The central store has its own retention and deletion policies.

Therefore, define your requirements separately:

| Requirement | Appropriate mechanism |
| --- | --- |
| Do not fill up the node | Local file rotation/limits, disk pressure alerts |
| View logs from the last few minutes | Runtime/kubelet local logs |
| Search logs across days/weeks | Central log store and retention policy |
| Trace one request across multiple replicas | Trace/request ID, collector, search |
| Never lose audit events | Dedicated durable delivery/storage mechanism, with reconciliation |
| Delete data per policy | Store retention, access control, and deletion workflow |
| Predictable log costs | Log levels/sampling/quotas + volume monitoring |

**Rotation does not replace compliance retention.** You may need to keep audit logs longer, but you should not infinitely expand node disk capacity to achieve that. Data should be stored in a system designed for long-term retention.

## 16. How to test rotation in containers responsibly

Testing should separate **configuration correctness**, **rotation behavior**, **collector delivery path**, and **lifecycle**.

### 16.1. Verify configuration

- For Docker, verify the logging driver/`max-size`/`max-file` via `inspect` after the container is created.
- For Kubernetes, identify the kubelet/node runtime in use and actual rotation settings using authorized administrative tools.
- For Java `RollingFile`, verify the file path/rollingPolicy/retention and JVM write permissions.
- Do not merely see a `max-size` line in source files and conclude it is active at runtime.

### 16.2. Test behavior with sample logs

A safe procedure in a **test environment**:

1. Set a small but valid threshold, e.g., 1 MB, and a file count limit.
2. Emit sample events with an `event_code` and an incrementing sequence number.
3. Let total volume exceed the threshold multiple times, without using secrets or real data.
4. Observe configuration/driver and segments via supported administrative tools; do not manually edit internal runtime files.
5. Confirm that recent records remain readable.
6. Confirm that local disk usage does not grow unbounded for the same container once the policy is active.
7. If a collector is present, compare received sequences/offsets against emitted sequences to identify loss/duplication and latency.
8. Stop/delete the test and clean up resources according to procedure.

**Do not claim "the test passes if `docker logs` can read all old lines"**; the goal of local retention is to be able to delete old lines. To verify historical integrity, you must check the central store, delivery policy, and old rotated data.

### 16.3. Test across restarts or deployments

Create scenarios:

- Container restarts quickly after writing logs.
- Pod is replaced by a new Pod.
- Node experiences disk pressure.
- Collector stops for a period and then recovers.
- Multiple replicas log the same event code with different trace IDs.
- An exception with a multiline stack trace.
- Pipeline needs to read old logs right when the node rotates.

Only simulate failures in authorized environments. Do not induce real disk pressure in production to see whether kubelet evicts pods.

### 16.4. Metrics to monitor

- Local log size and growth rate on nodes/volumes.
- Rotation count and rotation errors if the platform exposes metrics.
- Collector queue/buffer size, dropped/retried record counts.
- Ingest latency from event emission to appearance in the central store.
- ERROR/WARN counts by event code, avoiding double-counting a single failure.
- Number of nodes/pods evicted or showing storage warnings.
- Storage cost and data volume by service/environment.

Not all runtimes share the same metric names; use the specific telemetry of your deployed system.

## 17. Common mistakes when handling rotation in containers

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Node disk fills up even though app only uses stdout | Log driver has no limits, kubelet rotation misconfigured, or excessive logging | Check runtime, kubelet, local usage, and log generation rate. |
| Docker `max-file` is set but files still grow | Missing `max-size` or old container was not recreated | Verify effective options on the container. |
| Logback `RollingFile` works but Docker logs remain huge | Java also writes to stdout; this is a separate path | Check both appenders and logging drivers. |
| Docker rotation does not shrink `/app/logs` files | Files are written directly by Java, not via stdout/stderr | Use a `RollingFile` policy or a separate file rotation process. |
| `kubectl logs --previous` does not show rotated logs | `--previous` is the previous container instance, not older segments | Use the collector/central store to search history. |
| Container restart loses old logs | Data was only on the runtime node, deleted/GC'd, or unshipped by collector | Investigate pipeline lifecycle and retention. |
| Collector drops chunks of data | Rotation faster than reads, backpressure, wrong parser, node loss | Compare sequences, offsets, queues, and ingest latency. |
| One stack trace becomes multiple fake events | Collector fails to merge multiline/partial records properly | Use JSON escaping or configure multiline/CRI parsers. |
| Two replicas writing to a shared file corrupt it | Rolling the same path on a shared volume | Separate files per instance or use stdout + collector. |
| File is renamed but writes still go to the old file | Logger holds the old file descriptor | Coordinate rotation/reopen; do not arbitrarily rename externally. |
| `copytruncate` loses a few lines | Application writes while the file is being copied/truncated | Avoid combining two unsynchronized rotation mechanisms. |
| Cannot create `/app/logs` | Container runs as non-root, volume has wrong permissions | Check UID/GID, mounts, and write permissions. |
| JSON logs fail to parse | Hand-built JSON via patterns, unescaped newlines/quotes | Use a supported JSON encoder and test the parser. |
| Setting a tiny `max-size` loses investigation logs | Local retention is too short relative to ingest speed | Tune storage/collector and reduce log volume at the source. |
| Logs appear in Docker but not in the central store | Collector is not reading, filter/route bug, or wrong index | Inspect the entire pipeline rather than just rotation. |
| ERROR logs are delivered multiple times | Multiple appenders/routes, retries, or multiple Java layers logging | Distinguish event IDs and per-destination routes. |

## 18. Practice exercises with answers

### Exercise 1: Two types of rotation

A Logback application has a `RollingFileAppender` writing to `/app/logs/app.log`. Docker is configured with `--log-driver json-file --log-opt max-size=10m --log-opt max-file=3`. Will the Docker configuration automatically rotate `app.log`?

**Answer:** No. The Docker driver handles container stdout/stderr; `app.log` is a file opened directly by the JVM. If both `ConsoleAppender` and `RollingFileAppender` are running, you must manage **two separate log paths**, not confuse them as one.

### Exercise 2: Kubernetes configuration

A team puts the following in a Pod manifest:

```yaml
env:
  - name: containerLogMaxSize
    value: "10Mi"
```

Will kubelet automatically apply that limit?

**Answer:** Not merely because this environment variable is present. `containerLogMaxSize` is a kubelet configuration property, not a standard container environment variable. If node-level rotation is needed, configure the node/kubelet layer properly via your cluster management tools.

### Exercise 3: Logs after many rotations

Docker limits local logs to at most three files, and the service writes many lines per second. Can you rely on `docker logs` to find all logs from last week?

**Answer:** No. Local retention by **size and file count** may only span a few minutes; containers and nodes also have their own lifecycles. You must ship logs to a central store with appropriate retention if you need long-term data lookup.

### Exercise 4: `kubectl logs --previous`

A Pod's logs have rotated three times, but the container has not restarted. Can you use `kubectl logs --previous` to read the immediately preceding rotated file?

**Answer:** No. That option refers to the **previous container run**, not the previous file segment. Rotated logs may be outside the scope of data served by the kubelet API; you must rely on your collection pipeline.

### Exercise 5: Non-root image

A Java image uses `USER 10001` and Logback writes to `/app/logs/app.log`. On deploy, the appender reports it cannot create the file. Should you increase `max-file` in Docker or do something else?

**Answer:** This is a **file path/write permission issue inside the container**, not Docker log rotation. Check the directory, mount, UID/GID, and security context; or switch to stdout to avoid needing dedicated writable files.

### Exercise 6: Rotation and data loss

The collector is down for 20 minutes, while the runtime rotates and deletes old logs after a few minutes due to high log volume. When the collector recovers, is it guaranteed to retrieve all logs?

**Answer:** No. Files deleted before being read will not magically reappear. You need to increase buffer/retention capacity appropriately, reduce log volume, monitor backpressure, and design storage/delivery mechanisms that meet real-world requirements.

### Exercise 7: Two replicas sharing a rolling file

Two Java Pods mount the same PVC and both write to `/logs/application.log` using `RollingFileAppender`. What is the risk?

**Answer:** Two JVMs can concurrently write/rename/roll over the same path, leading to file conflicts, interleaved logs, data loss, or corrupted rolling metadata. You should separate paths per instance or use stdout with a node-level collector to avoid shared files.

### Exercise 8: Testing end-to-end architecture

You have just configured Compose with `max-size=1m` and `max-file=3`. Propose assertions that do not require retaining the entire log history.

**Suggested answer:**

1. `docker inspect` shows the correct driver/options on the actual container.
2. Run the sample program with log volume exceeding the threshold.
3. The runtime still records the most recent events and the app does not error as logs grow.
4. Local disk usage obeys the rotation policy when observed with supported tools.
5. The collector (if any) receives data and tracks completeness/duplication/loss per system targets.
6. Container restart/replacement is tested separately against expected retention.
7. Clean up test containers and files safely.

## 19. Deployment checklist for Java container rotation

Before moving to production, verify:

- [ ] **Path:** Does Java write to stdout/stderr or to files? Are there multiple appenders for the same event?
- [ ] **Rotation owner:** Docker driver, kubelet/node runtime, or Logback/Log4j 2?
- [ ] **Size:** Are `max-size`/`containerLogMaxSize`/`maxFileSize` suited to the log rate?
- [ ] **Count/retention:** Are the segment count or retention days suited to short-term lookup needs?
- [ ] **Lifecycle:** To what extent does data survive container restarts, pod replacement, and node loss?
- [ ] **Collection:** Can the collector read fast enough before old files are deleted?
- [ ] **Observability:** Are there metrics for disk pressure, dropped logs, queues, and ingest lag?
- [ ] **Security:** Are secrets excluded from logs, and are read permissions and retention periods appropriate?
- [ ] **Correctness:** Are stack traces, Unicode, JSON Lines, and partial records parsed cleanly?
- [ ] **Multi-replica:** Are multiple processes prevented from rotating the same file on a shared volume?
- [ ] **Runtime verification:** Are options actually active, not just present in YAML/XML source?
- [ ] **Testing:** Are there tests for log volume, rotation, temporary collector outages, and restarts?
- [ ] **Investigation plan:** When `docker logs`/`kubectl logs` no longer has history, do you know which store to search?
- [ ] **Responsibility boundary:** Do critical audit/reconciliation events use an appropriate durable mechanism rather than console logs alone?

**Conclusion:** For most containerized Java services, prefer **ConsoleAppender → stdout/stderr → runtime/kubelet rotation → collector**, with each layer having a clear responsibility. When an application needs dedicated files, use a rolling policy with clear ownership and verify volumes/sidecars. Rotation only bounds **local** logs; long-term investigation capability and protection against data loss depend on a verified collection pipeline, storage, and retention policy.
