# server.shutdown and Default Differences Across Spring Boot Versions

## 1. Objectives and key takeaway

An in-flight HTTP request can be cut off mid-execution when a Spring Boot application shuts down due to a new version deploy, scale-down, container restart, or manual operation. **Graceful shutdown** lets the embedded web server stop accepting new requests while giving running requests **a chance to finish within a limited time budget**.

Spring Boot has the **`server.shutdown`** property with two values:

- **`immediate`:** stops the embedded web server without actively draining running HTTP requests.
- **`graceful`:** stops accepting new requests and waits for in-flight requests to complete **until the grace period expires**, then continues lifecycle shutdown.

**Version milestone to memorize:** Spring Boot **2.3–3.3 defaults to `immediate`**, whereas **starting in Spring Boot 3.4 the default is `graceful`**. Version 2.3 was when graceful shutdown was introduced for embedded web servers; do not confuse **starting to support** with **enabled by default**.

This lesson belongs to the **Graceful Shutdown** group in the **Spring Boot - web-runtime** module. After completing it, you can:

1. State the exact default value of `server.shutdown` across Spring Boot generations.
2. Distinguish shutdown **mode** from `spring.lifecycle.timeout-per-shutdown-phase`, HTTP client timeouts, and Kubernetes termination budgets.
3. Describe the process of closing `ApplicationContext`, stopping `SmartLifecycle` beans, and the shutdown hook.
4. Write and run a **Java 17 + Spring Boot 3.3.5** application with a slow endpoint, send `SIGTERM` while a request is running, and compare immediate/graceful/default.
5. Prove the default change in **Spring Boot 3.4.0** by changing the Maven parent and re-running the same experiment.
6. Explain differences across Tomcat, Jetty, Reactor Netty, and Undertow, as well as external WAR containers.
7. Design termination policies for Kubernetes, readiness, preStop, proxy draining, streaming, and background jobs.
8. Check common mistakes: `SIGKILL`, IDE Stop, not forwarding signals, insufficient timeouts, and assuming graceful guarantees exactly-once.

## 2. What happens when a busy application has to stop?

~~~text
Client A sends GET /api/work (8s processing)
       |
       v
Spring Boot embedded server :8080
       |
       | Request accepted -> controller is running
       |
Process receives SIGTERM
       |
       +--> immediate: starts stopping server without waiting for a separate drain
       |        '--> running request may error/drop response
       |
       '--> graceful: stops accepting new requests
                |---> request A can complete within grace window
                '---> when no active requests remain or timeout expires
                      proceeds to close web server / context
~~~

An **in-flight request** is a request already accepted by the server before shutdown begins; a **new request** is one arriving after the server stops accepting traffic. Classification near the boundary may experience races; new TCP connections, HTTP keep-alive, queued requests, or reverse proxies may not behave identically.

In graceful mode:

- **Already running** requests get a chance to return a complete HTTP response.
- **New** requests are rejected in a way that depends on the embedded server and network.
- It is not required to wait the full 20/30 seconds; if all requests finish early, the server can exit sooner.
- When the budget expires, the server may close active connections and clients see a reset, EOF, or incomplete response.
- There is no guarantee that the client is still waiting, that DNS/proxy won't error, or whether business side effects committed or not.

**Graceful ≠ immortal, and immediate ≠ every request is guaranteed to fail.** Graceful simply improves the probability of completing HTTP exchanges during an **intentional and properly executed** shutdown.

## 3. Version table: the default change in Boot 3.4

This is the most important part because older tutorials state a different default than newer tutorials:

| Spring Boot version | Embedded graceful shutdown feature | `server.shutdown` when unconfigured |
| --- | --- | --- |
| **2.2 and earlier** | Standard graceful property/integration introduced in 2.3 was not present | Same mechanism not applicable |
| **2.3.x** | Yes; introduced in 2.3 | **`immediate`** |
| **2.4–2.7** | Yes | **`immediate`** |
| **3.0–3.3** | Yes | **`immediate`** |
| **3.4.x** | Yes; **default changed** in 3.4 | **`graceful`** |
| **3.5.x** | Yes | **`graceful`** |
| **4.0/4.1** | Yes for the embedded web servers listed in that version's docs | **`graceful`** |

Primary documentation sources:

- **Spring Boot 2.3 Release Notes** introduce “Graceful shutdown” and require enabling via `server.shutdown=graceful`.
- **Spring Boot 3.3 Reference** states “To enable graceful shutdown” with the configuration `server.shutdown=graceful`.
- **Spring Boot 3.3 Common Application Properties** lists the default of `server.shutdown` as **`immediate`**.
- **Spring Boot 3.4 Release Notes** announce embedded web-server graceful shutdown is **“now enabled by default”**; the old behavior can be restored with `server.shutdown=immediate`.
- **Spring Boot 3.4 and 3.5 docs** state graceful is “enabled by default”; 3.4 common properties list the default as **`graceful`**.
- **Spring Boot 4.x docs** continue describing graceful as the default, though the list of embedded web servers may differ from 3.x; check the exact branch.

**Version-pinned URLs** are in the references section to avoid reading the latest `/reference/` page by mistake and projecting it onto 3.3.

### 3.1. Two seemingly contradictory statements that are both true for their time

- “To get graceful, set `server.shutdown=graceful`”: true as the instruction to enable the feature in **Boot 2.3–3.3**.
- “Graceful is enabled by default”: true from **Boot 3.4 onward**, when the app uses a supported embedded server and has no override.

Never say “Spring Boot defaults to immediate” or “Spring Boot defaults to graceful” without stating the version. Both settings **remain valid** after the default changed; changing the default did not remove the `immediate` option.

### 3.2. Upgrading versions can change operations without changing application.properties

Suppose a project uses Boot 3.3.5 and the config file omits `server.shutdown`. After bumping the parent/BOM to 3.4.0, the new artifact will choose graceful instead of immediate. A rollout may therefore stop more slowly and require an adjusted termination budget, in exchange for reduced risk of cutting off requests.

If shutdown behavior matters, **configure it explicitly** instead of relying on defaults, especially during version upgrades.

## 4. server.shutdown and spring.lifecycle.timeout-per-shutdown-phase differ

Example Boot 3.3.5 config to enable graceful:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

| Property | Role | Typical default |
| --- | --- | --- |
| `server.shutdown` | Chooses **immediate** or **graceful** for the embedded web server | Boot ≤3.3: immediate; Boot ≥3.4: graceful |
| `spring.lifecycle.timeout-per-shutdown-phase` | Maximum time to stop **each phase** of `SmartLifecycle` bean groups | **30s** in Boot 3.3/3.4 |
| `server.port` | HTTP listener port | Usually 8080 |
| `server.tomcat.connection-timeout` | Timeout for part of a Tomcat TCP/HTTP connection lifecycle | Not a grace period |
| `spring.task.execution.shutdown.await-termination` | Lets the auto-configured executor wait for running jobs | false in Boot 3.3 |
| `spring.task.scheduling.shutdown.await-termination` | Lets the auto-configured scheduler wait for running jobs | false in Boot 3.3 |

`spring.lifecycle.timeout-per-shutdown-phase=20s` does **not** mean:
- The JVM always exits after exactly 20 seconds.
- Every normal HTTP request is limited to at most 20 seconds.
- Every DB, Kafka, or RestClient/WebClient operation automatically times out at 20 seconds.
- The total closing time of all phases/beans is guaranteed not to exceed 20 seconds.

It is a budget **per shutdown phase** of `LifecycleProcessor`. Multiple phases and bean destruction can add time. Nor is the grace period a mandatory delay: if no active requests remain, the phase can finish before the timeout.

### 4.1. application.yml

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

### 4.2. Command-line override

~~~bash
java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar \
  --server.shutdown=graceful \
  --spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

The command above is for POSIX shells. For Windows PowerShell, write it on a single line or use PowerShell's own line-continuation syntax instead of a backslash.

### 4.3. Environment variables

~~~bash
export SERVER_SHUTDOWN=graceful
export SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE=20s
java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar
~~~

Spring Boot relaxed binding maps env vars to properties. If a profile, CLI args, or a higher-priority property source overrides them, the **effective** value can differ from what you read in `application.properties`. When diagnosing production, check Helm values, env, ConfigMaps, command-line args, and the runtime artifact.

### 4.4. Explicit choice based on goals

~~~properties
# Policy wanting HTTP drain on both Boot 3.3 and 3.4:
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Or:

~~~properties
# Need to restore old behavior in Boot 3.4+:
server.shutdown=immediate
~~~

Setting immediate can help stop faster but may increase errors from in-flight requests; you must accept that trade-off after evaluating the workload.

## 5. Spring Context and SmartLifecycle: where does shutdown happen?

Spring Boot applications typically register a **JVM shutdown hook** for the `ApplicationContext`. When the Java process receives a signal handleable by the JVM such as `SIGTERM`, Spring proceeds to close the context.

~~~text
SIGTERM -> Java shutdown hook
                |
                v
        Closing ApplicationContext
                |
                v
        Stop SmartLifecycle phases
                |
                +--> web server graceful drain
                |     (earliest phase of stopping)
                |
                +--> stop other SmartLifecycle beans
                |
                v
        Bean destruction callbacks
        (@PreDestroy, DisposableBean, destroy methods)
                |
                v
        Resource cleanup and process exit
~~~

The diagram above is an overview and **does not guarantee the absolute order of every custom bean**. Spring Boot docs state that web-server graceful shutdown is performed in the **earliest phase of stopping SmartLifecycle beans**. When you have custom executors, consumer lifecycles, or clients, you must verify their specific phases/dependencies.

### 5.1. Phase ordering and timing

`SmartLifecycle` has methods such as `start()`, `stop(Runnable callback)`, and `getPhase()`. Spring organizes stopping by phases; beans in the same phase can stop in parallel/concurrently per lifecycle processor semantics. **Timeout-per-shutdown-phase** limits the processing time of one phase, not the total number of phases.

Hypothetical example:

~~~text
Web server drain phase:       12s
Message consumers phase:       8s
Bean/resource destruction:     3s
----------------------------------
Total closing time:           23s
~~~

Even if timeout-per-phase is 20s, the total can be **23s** without any single phase exceeding its budget. This is an illustrative calculation, not a real measurement or a contract that phase order is fixed as shown.

### 5.2. Graceful does not stop all workloads under the same policy

Even after web requests have drained:
- A `@Scheduled` job might still be running.
- Kafka/Rabbit consumers have their own lifecycles.
- Custom thread pools might keep threads alive.
- The JDBC connection pool must remain alive long enough for requests still using it.
- Tracing/logging exporters may need to flush.
- Long-lived WebSocket/SSE connections or streams may exist.

You must configure shutdown for these components **separately** from `server.shutdown`, rather than relying on one flag to cover everything.

## 6. Embedded web servers: not all return HTTP 503

In **Spring Boot 3.3/3.5**, graceful shutdown docs list four embedded servers: **Tomcat, Jetty, Reactor Netty, Undertow**. During graceful shutdown, how new requests are rejected differs:

| Server | New request rejection behavior per Boot 3.x docs |
| --- | --- |
| **Tomcat** | Stops accepting new requests at the network layer |
| **Jetty** | Stops accepting new requests at the network layer |
| **Reactor Netty** | Stops accepting new requests at the network layer |
| **Undertow** | May accept new connections but returns **HTTP 503 Service Unavailable** immediately |

**Do not expect a single fixed status across all of them.** On Tomcat/Jetty/Netty, curl may see connection refused, reset, or connection closed instead of an HTTP 503 response. With Undertow on supported branches, 503 may be seen. If a request arrives right at the moment of shutdown, the outcome also depends on races/network/proxies.

**Caution with Spring Boot 4.x:** current documentation lists Tomcat, Jetty, and Reactor Netty in the graceful shutdown section. Do not copy Boot 3.x's Undertow matrix and claim the same support in every 4.x version without verifying the corresponding module/container.

### 6.1. External WAR container limitations

`server.shutdown` manages the **embedded web server owned by Spring Boot**. When deploying a WAR into an **external Tomcat/Jetty** managed outside the app, draining the listener is that container's and infrastructure's responsibility. Setting `server.shutdown=graceful` inside the WAR alone is not enough to force an external container to stop accepting HTTP according to your policy; consult the application server/ingress configuration separately.

### 6.2. Keep-alive, HTTP/2, and reverse proxies

HTTP keep-alive connections may exist prior to shutdown. A new HTTP request on an old connection may also be rejected during drain, depending on the implementation. HTTP/2 multiplexes multiple streams over a connection, so GOAWAY/stream draining semantics differ from HTTP/1.1. Proxies/ingresses have their own connection reuse, so test in reality if the app serves traffic behind a load balancer.

## 7. SIGTERM, SIGINT, and SIGKILL: conditions for graceful to actually run

| Stop method | Chance of running Spring/JVM cleanup | Notes |
| --- | --- | --- |
| `SIGTERM` to Java PID | Yes, via normal lifecycle path | Reliable test method on Linux/Unix/K8s |
| `SIGINT` or `Ctrl+C` | Usually yes, depending on terminal and runtime | Need to know what signal the tool/process manager sends |
| `SIGKILL` / `kill -9` | **No** | JVM does not run shutdown hooks |
| IDE Stop / Terminate | Depends on IDE | Some IDEs kill the process immediately, not gracefully |
| Process crash/JVM fatal issue | Not guaranteed | Cleanup may not run |
| `ApplicationContext.close()` | Triggers context lifecycle | Not completely identical to deployment SIGTERM |
| Container stop | Usually TERM then KILL if grace budget expires | PID 1, wrappers, orchestrator affect behavior |

By default, SpringApplication registers a shutdown hook to close the context. If a developer disables the hook or the process is forcefully killed, even with the property set to `graceful`, it still may not drain.

### 7.1. Docker ENTRYPOINT and PID 1

A Docker image should forward signals to Java properly:

~~~dockerfile
# End of Dockerfile, once the image has JRE and app.jar:
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Whereas shell form:

~~~dockerfile
# Prone to issues if the shell does not forward signals:
ENTRYPOINT java -jar /app/app.jar
~~~

can cause Java to run under a PID 1 shell and fail to receive TERM as expected. If a wrapper script is needed, use `exec java -jar ...` or an appropriate init/process manager, then **test it in practice**. Do not deduce from a “Starting” log line that TERM definitely reaches the Java process.

### 7.2. Why testing from an IDE can give misleading results?

Spring Boot docs note that IDEs may stop a process via a mechanism that does not send a proper `SIGTERM`, causing graceful shutdown not to happen as expected. That is why the lab below builds an executable JAR and uses `kill -TERM` directly on the Java PID, rather than just clicking Stop and concluding the config is wrong.

## 8. Lab: Spring Boot 3.3.5, Java 17, 8-second request

Create a small project with:
- `GET /api/ping` returning a fast response.
- `GET /api/work?ms=8000` processing for 8 seconds with `Thread.sleep` (for illustration only).
- `application.properties` **without `server.shutdown`**, to test Boot 3.3's default.
- A Bash script that launches Java directly, waits for the server to be ready, sends a slow request, sends TERM mid-flight, and records curl output and server logs.

### 8.1. File structure

~~~text
shutdown-lab/
├── pom.xml
├── run-case.sh
└── src/main/
    ├── java/com/example/shutdown/
    │   ├── ShutdownLabApplication.java
    │   └── WorkController.java
    └── resources/
        └── application.properties
~~~

Practice on Linux/macOS/WSL with Bash/curl/Maven/JDK 17. Both Spring Boot 3.3.5 and 3.4.0 run on Java 17 for the lab's code scope. Do not run forced-stop experiments on production.

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>shutdown-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`spring-boot-starter-web` brings MVC and embedded Tomcat. `spring-boot-starter-actuator` helps probe health/readiness; Actuator is not required for the graceful property to work.

### 8.3. Main class

**File `src/main/java/com/example/shutdown/ShutdownLabApplication.java`:**

~~~java
package com.example.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownLabApplication.class, args);
    }
}
~~~

### 8.4. WorkController.java

**File `src/main/java/com/example/shutdown/WorkController.java`:**

~~~java
package com.example.shutdown;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class WorkController {

    private final AtomicInteger sequence = new AtomicInteger();

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/work")
    public ResponseEntity<String> work(
            @RequestParam(defaultValue = "8000") int ms) {
        if (ms < 0 || ms > 30000) {
            return ResponseEntity.badRequest().body("invalid ms");
        }

        int id = sequence.incrementAndGet();
        System.out.printf(
                "START id=%d ms=%d at=%s thread=%s%n",
                id, ms, Instant.now(),
                Thread.currentThread().getName());

        try {
            Thread.sleep(ms); // LAB ONLY.
            System.out.printf(
                    "FINISH id=%d at=%s%n",
                    id, Instant.now());
            return ResponseEntity.ok("completed:" + ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.printf(
                    "INTERRUPTED id=%d at=%s%n",
                    id, Instant.now());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted:" + ms);
        }
    }
}
~~~

**Analysis:**

1. `AtomicInteger` assigns IDs to requests (resets on restart) to help identify them in logs.
2. `/api/ping` is a control endpoint to tell when the server is ready.
3. `Thread.sleep(ms)` **intentionally** holds a Tomcat worker. In production, do not sleep in a controller to process business logic.
4. When finished waiting, the server logs `FINISH` and attempts to return body `completed:8000`.
5. If the thread is interrupted, the code logs `INTERRUPTED` and tries to return 503; if the connection has closed, the client is **not guaranteed to receive the body**. Do not infer solely from the FINISH log that the browser received the full response.
6. `ms` is bounded to 0..30000 to avoid letting a demo parameter hold a worker arbitrarily long; the lab binds only to localhost.

### 8.5. application.properties

**File `src/main/resources/application.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.lifecycle.timeout-per-shutdown-phase=20s

# INTENTIONALLY DO NOT SET server.shutdown HERE.
# Test each Boot version's default and CLI overrides.

management.endpoints.web.exposure.include=health,info
management.health.probes.enabled=true
management.endpoint.health.show-details=never
~~~

Do not declare `server.shutdown` in the shared file so we can test the default. Adding `server.shutdown=graceful` here would mean the 3.3 default case is no longer actually testing the default.

### 8.6. Maven build

In the `shutdown-lab` directory:

~~~bash
mvn clean package
java -version
~~~

Artifact:

~~~text
target/shutdown-lab-0.0.1-SNAPSHOT.jar
~~~

Run the executable JAR directly when testing signals; `mvn spring-boot:run` can add a process/plugin layer, making it harder to be sure the signal hit the right Java PID.

## 9. run-case.sh: automating SIGTERM and in-flight request tests

**File `run-case.sh`**, created next to `pom.xml`:

~~~bash
#!/usr/bin/env bash

# CASE is taken from arg 1; defaults to 'default' if omitted.
CASE=default
if [ "$#" -ge 1 ]; then
    CASE="$1"
fi

MODE_ARG=""
if [ "$CASE" = "graceful" ]; then
    MODE_ARG="--server.shutdown=graceful"
elif [ "$CASE" = "immediate" ]; then
    MODE_ARG="--server.shutdown=immediate"
elif [ "$CASE" != "default" ]; then
    echo "Usage: bash run-case.sh default|graceful|immediate" >&2
    exit 2
fi

JAR=target/shutdown-lab-0.0.1-SNAPSHOT.jar
if [ ! -f "$JAR" ]; then
    echo "Missing jar: run mvn clean package" >&2
    exit 2
fi

# Run JAVA command in background and save PID.
# Unquoted $MODE_ARG produces either one CLI arg or none.
java -jar "$JAR" $MODE_ARG \
    --spring.lifecycle.timeout-per-shutdown-phase=20s \
    > server.log 2>&1 &
APP_PID=$!

cleanup() {
    kill -TERM "$APP_PID" 2>/dev/null || true
}
trap cleanup EXIT

READY=no
for i in $(seq 1 60); do
    if curl -fsS --max-time 1 \
        http://127.0.0.1:8080/api/ping \
        > /dev/null 2>&1; then
        READY=yes
        break
    fi
    sleep 1
done

if [ "$READY" != "yes" ]; then
    echo "Server not ready; inspect server.log" >&2
    exit 1
fi

echo "App PID=$APP_PID case=$CASE ready"

# Send an 8-second request to the server.
curl -sS --max-time 18 \
    -w '\nHTTP_STATUS=%{http_code}\nTOTAL_SECONDS=%{time_total}\n' \
    'http://127.0.0.1:8080/api/work?ms=8000' \
    > client.out 2> client.err &
CURL_PID=$!

# Let controller start, then send TERM to the JVM.
sleep 2
echo "Sending SIGTERM to Java PID=$APP_PID"
kill -TERM "$APP_PID"

# Do not use set -e, so results still print even if curl fails.
wait "$CURL_PID"
CURL_EXIT=$?
echo "curl exit code=$CURL_EXIT"
echo "--- client.out ---"
cat client.out
echo "--- client.err ---"
cat client.err

wait "$APP_PID" 2>/dev/null
trap - EXIT

echo "--- app shutdown log excerpts ---"
grep -E 'START id=|FINISH id=|INTERRUPTED id=|Graceful' \
    server.log || true
~~~

The script is sufficient to run on Bash/Linux/macOS/WSL with `curl`, `seq`, JDK 17, and Maven. **Do not run multiple cases concurrently**, because they share port 8080. The script creates `server.log`, `client.out`, and `client.err` and **overwrites** them on the next run; rename the logs after each run if you need to preserve evidence.

**Race warning:** `sleep 2` is normally enough for the controller to log `START` on an ordinary local machine. On an overloaded machine, if `START` has not appeared in `server.log` before SIGTERM, try increasing the delay or adding test synchronization; do not use a request that has not started yet to conclude graceful shutdown does not work.

### 9.1. Running the 3 cases

~~~bash
mvn clean package

bash run-case.sh graceful
bash run-case.sh immediate
bash run-case.sh default
~~~

`CASE=default` keeps `MODE_ARG` empty so the app uses the real default (if no env/other property overrides it). `CASE=graceful` and `CASE=immediate` pass the corresponding CLI arg.

### 9.2. Expectations for graceful on Boot 3.3.5

The `8000ms` request logged `START` before receiving TERM; grace period per phase is `20s`. Under normal conditions, the server can drain successfully:

~~~text
START id=1 ms=8000 at=... thread=http-nio-8080-exec-...
FINISH id=1 at=...
~~~

The client response typically contains:

~~~text
completed:8000
HTTP_STATUS=200
~~~

Timestamps/thread names/total time may vary. If the client/proxy times out early on its own or the process is force-killed, the result can differ even with graceful enabled. Once all active requests finish, the process normally closes **without waiting the full 20 seconds**.

### 9.3. Expectations for immediate

With the server stopping before the controller returns a response, the client may get a `curl` error:

~~~text
curl: (52) Empty reply from server
~~~

or:

~~~text
curl: (56) Recv failure: Connection reset by peer
~~~

or another outcome depending on OS, container, and race. Without an HTTP response, `HTTP_STATUS` from curl may be `000`. These are **possible examples**, not deterministic output; immediate simply does not actively drain, and does not guarantee every request must fail.

### 9.4. Default case on 3.3.5

When `server.shutdown` is undeclared, **Boot 3.3.5 defaults to immediate**, so the default case usually unfolds similarly to explicit immediate. If not, check `SERVER_SHUTDOWN`, command line, environment, profiles, artifact version, and whether the request logged START before TERM.

## 10. Repeat the same lab on Boot 3.4 to see the default change

How to verify by exact version:

1. Copy the project into another lab directory or record a Git diff (do not lose the 3.3 version).
2. In `pom.xml`, change **only the Spring Boot parent version** `3.3.5` to **`3.4.0`**.
3. Keep the Java controller and script identical.
4. Do not add `server.shutdown` to `application.properties` and set no env overrides.
5. Rebuild and run default, then explicit immediate:

~~~bash
mvn clean package
bash run-case.sh default
bash run-case.sh immediate
~~~

In `pom.xml` after the change:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
</parent>
~~~

**Important expectation:** on **3.4.0**, the `default` case behaves like `graceful` because Boot 3.4 changed the default; the `immediate` case still restores the old shutdown behavior. This is confirmed by the 3.4 Release Notes and config metadata.

In practice, upgrading 3.3 → 3.4 involves many other dependency/API changes. Do not treat a simple lab as proof that a production project is automatically compatible; you must test framework/security/data integrations and deployment.

## 11. What happens when the grace period expires?

Suppose a request takes 15 seconds but you configure:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=3s
~~~

If SIGTERM arrives when the request has only run for 1 second, the web server only has **around 3 seconds** in the drain phase to wait. If the request has not completed, shutdown proceeds; the response may be cut off, the socket closed, and the client reports an error. **There is no guarantee that every 15s request finishes.**

Conversely, an 8s request with a 20s phase limit usually finishes in time. This is a limit **during shutdown**; during normal operation, requests are still subject to separate HTTP/client/proxy timeouts.

### 11.1. “20 seconds” is not the total JVM deadline

If the lifecycle has multiple phases and resource cleanup, total stop time may exceed 20s. If an orchestrator has `terminationGracePeriodSeconds=15`, `SIGKILL` can happen **before** the 20s phase timeout expires; Spring configuration cannot force Kubernetes to wait longer than its policy.

### 11.2. What about unbounded requests: WebSocket/SSE/long polling?

A WebSocket can stay open for hours; an SSE/`Flux.never()` may never complete. If you rely on graceful shutdown to wait for them to finish on their own, shutdown can time out. You need to design:

- Actively closing the stream and signaling a server-draining event.
- Client reconnect/backoff and re-subscribe/data recovery.
- Checkpoints/offsets/replay if messages must not be lost.
- Limiting session idle/max duration and handling cancellation.
- Not relying on `server.shutdown=graceful` as a durable delivery mechanism.

## 12. Readiness and lifecycle in Kubernetes

Terminating a Pod is not just a single Java method call:

~~~text
Kubernetes starts terminating Pod
       |
       +--> updates terminating status/EndpointSlices
       |    LBs/ingresses need time to sync
       |
       +--> preStop hook (if any)
       |
       +--> sends SIGTERM to process in container
       |
       +--> Spring closes ApplicationContext
       |      +--> ReadinessState = REFUSING_TRAFFIC
       |      '--> web server stops accepting new HTTP requests
       |            and drains in-flight if graceful
       |
       +--> background components / resources shutdown
       |
       '--> if termination budget expires before exit: SIGKILL
~~~

**`terminationGracePeriodSeconds` starts counting from when termination begins, including the preStop hook.** Do not add a 5s preStop and a 30s grace and forget that the total Pod budget is still 30s. If shutdown has multiple phases, budget extra time.

### 12.1. Illustrative Kubernetes YAML

This is a **fragment inside a Pod template**, not a complete Deployment manifest:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      image: example/shutdown-lab:1.0
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
        failureThreshold: 2
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
      env:
        - name: SERVER_SHUTDOWN
          value: graceful
        - name: SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE
          value: 25s
~~~

Explanation:

- `terminationGracePeriodSeconds:45` is the total time the Pod is awaited before force kill.
- `preStop sleep 5` gives a window for endpoint/ingress propagation **before SIGTERM**; these 5s are subtracted from the total budget. For distroless images lacking shell/sleep, another approach is needed.
- `25s` is **timeout per phase** in Spring, not a guaranteed total stop time of 25s.
- `image` is illustrative only and requires building/pushing a real image; `Spring Boot Actuator` must be in the application for probe routes to exist.
- Choosing 45s is just an example: you must measure drain time, other phases, preStop, readiness propagation, and safety margin.
- Do not expose Actuator management endpoints publicly unnecessarily; use proper network security and probe permissions.

### 12.2. ReadinessState during shutdown

Per Spring Boot Actuator docs, when an app is **Ready**, readiness is `ACCEPTING_TRAFFIC`; during **graceful shutdown**, readiness switches to `REFUSING_TRAFFIC` and new HTTP requests are rejected.

**Note:** the readiness HTTP endpoint may become **unreachable from outside as soon as the web server starts rejecting requests**, because the probe itself is a new HTTP request. Do not conclude readiness failed to update just because `curl /actuator/health/readiness` gets connection refused after TERM. Look at logs, earlier actuator availability events, EndpointSlice state, and proxy metrics.

### 12.3. preStop and rollout readiness do not replace each other

- Kubernetes can mark a Pod terminating so endpoint consumers stop picking that backend.
- Ingresses/service meshes/LBs may update slowly or hold open connections.
- A preStop delay can help reduce races in certain topologies, but does not guarantee every proxy has drained all connections.
- Embedded graceful drain is still needed if in-flight requests remain.
- Rolling updates must keep enough healthy pods ready to serve new traffic.

### 12.4. Budgeting based on measurements

Hypothetical example:

| Component | Measured time |
| --- | ---: |
| preStop/route propagation | 5s |
| request drain p99 | 12s |
| lifecycle phases, producer flush | 7s |
| safety margin | 8s |
| **Estimated total** | **32s** |

You can try a 45s Pod budget and 20–25s Spring shutdown phase timeout, then verify under real workload. These are not default production numbers valid for every service: image startup, proxies, phase counts, long polling, Kafka flushes, and databases can all change them.

## 13. @Async, @Scheduled, message consumers, and DB pool are separate concerns

`server.shutdown` **does not directly control** every task in the application. For example:

- A `@Scheduled` job running for 60 seconds.
- A message consumer processing a Kafka record.
- An `@Async` method calling an external API.
- A custom ExecutorService with unstopped threads.
- A JDBC transaction committing.
- A tracing exporter/log appender flushing buffers.

If you only enable web graceful shutdown while closing the DB pool/producer/executor before the work needing them finishes, the app can still suffer data errors.

### 13.1. Properties for auto-configured executor/scheduler in Boot 3.3

~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=20s

spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=20s
~~~

These properties apply to **Boot-managed task executors / schedulers via the appropriate mechanism**, and do not automatically close every manually created `Executors.newFixedThreadPool` in code. By default `await-termination=false` in Boot 3.3; you must sum timeouts/lifecycle phases.

If you create an executor manually:

1. Stop accepting new tasks.
2. Call `shutdown()` instead of `shutdownNow()` upfront if draining is needed.
3. Wait with a timeout.
4. Cancel/roll back/compensate the remainder when the budget expires.
5. Order resource/bean shutdown properly; do not close DB/HTTP clients while jobs still need them.

### 13.2. Exactly-once and idempotency do not come from graceful shutdown

A payment POST may have committed successfully while the response was lost during Pod restart. The client does not receive 200 and retries -> risk of **double charge**. Enabling graceful reduces the risk but does not guarantee exactly-once. You need `Idempotency-Key`/unique constraints, transaction boundaries, and appropriate outbox/ack policies.

Similarly, a consumer acking before commit can lose a message; a consumer acking after commit before shutdown can cause a duplicate upon redelivery. You need at-least-once/idempotent design, rather than treating `server.shutdown` as solving queue semantics.

## 14. MVC synchronous, MVC async, WebFlux, and streaming

Boot 3.3 docs describe graceful shutdown for embedded web servers in Servlet and reactive web apps; however, how work is held differs.

| Stack/request type | While request is running | What to test |
| --- | --- | --- |
| Spring MVC sync | Tomcat worker processes it, may wait on blocking I/O | Sufficient grace window and downstream timeouts |
| Spring MVC async | `Callable`/`DeferredResult`/`WebAsyncTask` has its own executor | Executor lifecycle, timeout, cancellation |
| Spring WebFlux | `Mono/Flux` publishers and Netty event loops | No blocking on event loop, cleanup on cancel |
| SSE/streaming | Response may last indefinitely | Finite drain period and resume/replay |
| WebSocket | Session may stay open for hours | Close/reconnect policy, connection drain |
| HTTP/2 | Multiple streams on one connection | GOAWAY/streams/new traffic semantics |

### 14.1. Standalone illustrative WebFlux snippet, not a full project

~~~java
package com.example.reactive;

import java.time.Duration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SlowReactiveController {

    @GetMapping("/reactive-work")
    public Mono<String> work(
            @RequestParam(defaultValue = "8") int seconds) {
        if (seconds < 0 || seconds > 30) {
            return Mono.error(new IllegalArgumentException(
                    "seconds out of range"));
        }
        return Mono.delay(Duration.ofSeconds(seconds))
                .thenReturn("completed:" + seconds);
    }
}
~~~

This snippet needs a **separate WebFlux project** with `spring-boot-starter-webflux`, a main class, and configuration—do not paste it into the MVC lab to compare API routes. `Mono.delay` does not block the event loop like `Thread.sleep`. Default graceful/immediate still depends on **Boot version/config**, not a WebFlux-specific property.

### 14.2. Why a short timeout does not fix streaming

If a request returns a continuous, non-ending `Flux.interval(...)`, a 20s graceful timeout will not make the stream “finish” on its own. The system must send a stream close, use checkpoints/event IDs/resume, close WebSockets normally, and force clients to reconnect to a new pod. Do not raise the timeout to hours to avoid designing session lifecycles.

## 15. Actuator shutdown endpoint IS DIFFERENT from server.shutdown property

Two similar names with different functions:

- **`server.shutdown`** is a setting for the embedded web server when the **context is closed**. It creates no new API.
- **`/actuator/shutdown`** is an Actuator endpoint that can request application shutdown **if enabled, exposed, and authorized** per configuration. This endpoint is **disabled by default**.

Therefore:

~~~properties
server.shutdown=graceful
~~~

does not mean the following HTTP request is automatically accepted:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

Spring Boot 3.4 also changed the endpoint access model compared to older versions, so do not copy Actuator endpoint-enabling instructions across versions without checking security/authorization. This lesson's lab **does not need** this endpoint enabled; using SIGTERM is the test path closest to deployment.

**Security:** do not open Actuator shutdown to the Internet; if used in an administrative workflow, it must have strict authentication/authorization/network policies.

## 16. Common operational pitfalls

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Boot 3.3 stops immediately when unconfigured | Default is immediate | Enable `server.shutdown=graceful` |
| Upgrading Boot 3.3 → 3.4 makes pods stop slower | Default changed to graceful | Measure drain, raise termination budget reasonably, or override intentionally |
| Graceful still cuts off requests in IDE | IDE Stop does not send proper SIGTERM | Use `java -jar` + `kill -TERM` |
| Using `kill -9` shows no cleanup | SIGKILL does not run hooks | Use TERM + budget |
| Container shows no Java shutdown logs | PID 1 shell does not forward signals | Exec-form ENTRYPOINT or `exec` wrapper |
| Grace window is 20s but JVM stops in 35s | Multiple lifecycle phases/destruction | Measure phases and resource shutdown |
| Grace window is 20s but client fails after 5s | 5s client/proxy timeout or connection reset | Check client/proxy deadlines |
| Tomcat does not return 503 during shutdown | Network-layer rejection | This is expected server-specific behavior |
| Undertow returns 503 for new requests | Boot 3.x Undertow behavior | Do not treat 503 as a graceful failure |
| `/actuator/health/readiness` unreachable after TERM | Web listener refuses new traffic | Observe availability/endpoint state externally |
| `@Scheduled` interrupted during HTTP graceful | Separate scheduler lifecycle | Configure await termination and job recovery |
| `@Async` unfinished when context closes | Unsuitable executor shutdown budget | Tune executor/lifecycle |
| WAR on external Tomcat does not drain as expected | Container is not owned by Boot | Configure external server draining |
| Duplicate payments after restart | Non-idempotent side-effect retry | Add idempotency/transactional handling |
| WebSocket/SSE blocks shutdown for long | Long-lived streams lack close policy | Proactively close/reconnect/resume |
| Increased grace period yet still killed | Short K8s terminationGracePeriodSeconds | Fit preStop + phases + cleanup under deadline |
| Config says graceful yet app behaves immediate | Env/CLI/profile override, wrong artifact | Verify effective property/Boot version |
| Test client had not logged START before TERM | Test race | Sync on START log or increase delay |

### 16.1. Ordered debugging workflow

1. Confirm the **Maven BOM / JAR runtime version** is actually 3.3, 3.4, or newer.
2. Confirm the **effective server.shutdown** after merging properties/env/CLI.
3. Confirm the process received **SIGTERM**, not SIGKILL/forced IDE terminate.
4. Confirm the request hit controller **START** before the signal.
5. Confirm the embedded web server type, not an external WAR.
6. Confirm `spring.lifecycle.timeout-per-shutdown-phase`, proxy/client timeouts, and Pod termination budget.
7. Check graceful start/complete logs and the client HTTP response **both status and body**.
8. Check other `SmartLifecycle` phases, executors, DB, messaging.
9. Test under a workload with concurrency, keep-alive, and long-lived connections.
10. Change only one variable at a time and re-measure error rate, latency, and shutdown duration.

## 17. Why does the version default matter during rolling updates?

**With Boot 3.3 default immediate:** when a Pod receives SIGTERM, in-flight requests are easily severed if the app does not enable graceful. If clients auto-retry, load can spike and cause duplicate non-idempotent operations.

**With Boot 3.4 default graceful:** Pods may stay alive longer during the grace window to finish running requests. If HPA/rollouts previously relied on fast stops, upgrading versions can slow down rollouts or hit `terminationGracePeriodSeconds` limits.

**With explicit configuration:** operators know the desired policy for certain. Good practices include:
- Writing `server.shutdown=graceful` explicitly even on 3.4.
- Choosing phase timeouts based on request SLOs and lifecycle phases.
- Calculating a full termination budget so SIGKILL never occurs before draining finishes.
- Ensuring enough healthy replicas are always available to serve new traffic during rolling updates.
- Having dashboards/alerts for 5xx, client resets, and shutdown duration.

There is no “just turn on graceful for zero downtime” silver bullet; you must coordinate application, client retries/idempotency, ingress, load balancer, and orchestration.

## 18. Additional hands-on exercises

### Exercise A — change duration

Run the server `graceful` with `spring.lifecycle.timeout-per-shutdown-phase=3s`, while sending `/api/work?ms=15000` before TERM. Predict that the client gets a severed response or reset, and explain why the property does not safely roll back a business transaction.

### Exercise B — test new requests while draining

While a slow request is running, send SIGTERM and then try:

~~~bash
curl -v --max-time 2 http://127.0.0.1:8080/api/ping
~~~

Once Tomcat has begun graceful drain, new requests are typically rejected at the network layer. On Undertow 3.x when similarly configured, docs describe new requests potentially receiving 503. Do not expect deterministic output if the Java process already exited or the request races with shutdown.

### Exercise C — observe default change via Maven parent

Build the same code on `3.3.5` and `3.4.0` **without** declaring `server.shutdown`. Run `bash run-case.sh default` and `bash run-case.sh immediate` for each version. Compare logs and client responses; explain why explicit settings beat defaults.

### Exercise D — check env/CLI precedence

~~~bash
export SERVER_SHUTDOWN=immediate

java -jar target/shutdown-lab-0.0.1-SNAPSHOT.jar \
  --server.shutdown=graceful
~~~

In Boot's standard config binding, the command-line property `--server.shutdown=graceful` takes precedence over the environment variable `SERVER_SHUTDOWN=immediate`. After the experiment:

~~~bash
unset SERVER_SHUTDOWN
~~~

In systems using special config sources, verify the effective value in the actual environment.

### Exercise E — stopping background jobs

Enable a scheduler or long async task and compare:

~~~properties
spring.task.scheduling.shutdown.await-termination=false
~~~

with:

~~~properties
spring.task.scheduling.shutdown.await-termination=true
spring.task.scheduling.shutdown.await-termination-period=15s
~~~

This is an **extension exercise requiring adding `@EnableScheduling` and a scheduled method in a separate project**; the original lab has no scheduled job. Explain why HTTP graceful differs from ensuring a job has committed and why extra shutdown phases must be accounted for.

## 19. Self-check questions

**Question 1.** Which Boot version introduced graceful shutdown support, and which version enabled it **by default**?

**Question 2.** How will Boot 3.3.5 stop when `server.shutdown` is undeclared? What about Boot 3.4.0?

**Question 3.** Which property disables graceful shutdown in Boot 3.4+?

**Question 4.** Does `timeout-per-shutdown-phase=20s` guarantee the JVM exits in exactly 20s?

**Question 5.** Why does setting `server.shutdown=graceful` not automatically create the HTTP endpoint `/actuator/shutdown`?

**Question 6.** On graceful Tomcat, must a new request necessarily receive HTTP 503?

**Question 7.** Why do `SIGKILL` and some IDE Stops prevent graceful shutdown from running?

**Question 8.** With K8s preStop 5s and terminationGracePeriodSeconds 30s, does Java still get a full 30s?

**Question 9.** Why does the FINISH log not prove the client received the full response?

**Question 10.** Does HTTP graceful guarantee `@Scheduled` jobs, Kafka consumers, and JDBC transactions complete?

**Question 11.** Why does graceful not guarantee exactly-once payment processing?

**Question 12.** When upgrading 3.3 → 3.4, why might rollouts become slower even though controller code did not change?

**Question 13.** Can `server.shutdown` be used to configure the listener of an external WAR container?

**Question 14.** Why might the readiness probe be unreachable while the app is shutting down gracefully?

**Question 15.** Name at least five metrics/measurements needed before choosing production shutdown timeouts.

**Answer guide:**

1. Feature since **2.3**; default graceful since **3.4**.
2. **3.3.5 immediate**, **3.4.0 graceful** if not overridden.
3. `server.shutdown=immediate`.
4. No; it is a budget per SmartLifecycle phase, not total stop time or a fixed delay.
5. The property is a web server shutdown policy; the Actuator endpoint is disabled by default and has separate access/exposure controls.
6. No, Tomcat usually rejects at the network layer; Undertow 3.x may return 503.
7. SIGKILL does not run shutdown hooks; IDEs may kill the process or fail to send proper TERM.
8. No. preStop is inside the total Pod termination budget.
9. Socket/proxy/client may have closed before response bytes finished transferring.
10. No. Each component needs its own lifecycle and executor/consumer policy.
11. Side effects may have committed even if the client lost the response; idempotency keys/unique constraints and proper transactions are required.
12. The new graceful default waits for in-flight requests instead of stopping immediately; proper budgets are needed.
13. Not solely via Boot's embedded server property; the external container controls the listener.
14. During graceful shutdown, the web server rejects new HTTP requests, including HTTP probes.
15. In-flight p99, stream durations, preStop, total phases, background jobs, proxy/client timeouts, Pod budget, resource cleanup, disconnect/error rate.

## 20. Production checklist

- [ ] Identified the actual Boot version of the artifact; not relying on “latest docs” when the project uses 3.3.
- [ ] Understood the 2.3 support milestone and the 3.4 default switch from immediate to graceful.
- [ ] Configured `server.shutdown` **explicitly** for critical workloads.
- [ ] Chose `spring.lifecycle.timeout-per-shutdown-phase` from real data, not guesses.
- [ ] Distinguished per-phase timeout, HTTP client/server timeouts, and total JVM shutdown time.
- [ ] JVM receives proper SIGTERM; Docker ENTRYPOINT/PID1 forwards signals accurately.
- [ ] Do not test graceful using kill -9 or IDE Stop with unclear mechanisms.
- [ ] Tested in-flight requests checking client status/body, not just the FINISH log.
- [ ] Tested that new requests are rejected according to the actual server implementation.
- [ ] Measured effects of keep-alive, HTTP/2, WebSocket, SSE, or long-polling if used.
- [ ] Separate lifecycles exist for `@Async`, `@Scheduled`, consumers, and custom executors.
- [ ] DB/HTTP pools are not closed before business work needing them finishes.
- [ ] Idempotency is implemented for operations unsafe on client retry.
- [ ] Readiness/liveness probes, ingress/LB drain policies, and rolling update headroom are in place.
- [ ] Pod termination budget covers preStop + Spring phases + cleanup + margin.
- [ ] Actuator shutdown endpoint is not exposed to the Internet.
- [ ] Tested before/after Boot version upgrades and recorded shutdown duration, resets, and error rates.

## 21. References

1. **Spring Boot 2.3 Release Notes** — introduces graceful shutdown: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.3-Release-Notes
2. **Spring Boot 3.3 Graceful Shutdown** — enabling `server.shutdown=graceful`, web server distinctions: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
3. **Spring Boot 3.3 Common Application Properties** — `server.shutdown` default `immediate`, shutdown phase timeout `30s`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
4. **Spring Boot 3.4 Release Notes** — graceful shutdown enabled by default: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
5. **Spring Boot 3.4 Graceful Shutdown** — default graceful mechanism: https://docs.spring.io/spring-boot/3.4/reference/web/graceful-shutdown.html
6. **Spring Boot 3.4 Common Application Properties** — default `server.shutdown=graceful`: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/
7. **Spring Boot 3.5 Graceful Shutdown** — default graceful: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
8. **Spring Boot 4.x Graceful Shutdown** — current documentation and list of embedded servers: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
9. **Spring Boot 3.3 Actuator Endpoints** — ApplicationAvailability, readiness during shutdown: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
10. **Spring Boot 3.3 Task Execution and Scheduling** — executor/scheduler lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
11. **Spring Boot 3.3 SpringApplication API** — shutdown hook: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
12. **Spring Framework SmartLifecycle** — phases and stop callbacks: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
13. **Kubernetes Container Lifecycle Hooks** — preStop: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
14. **Kubernetes Pod Termination** — grace budget/SIGKILL: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination
15. **Kubernetes Probes** — liveness/readiness/startup: https://kubernetes.io/docs/concepts/workloads/pods/probes/
