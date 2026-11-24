# Wait Strategies, Readiness, and Verifying a Service Is Truly Ready

## 1. Why does container RUNNING not mean service READY?

When testing a Spring Boot application with Testcontainers, Docker may report that a container is running while the service inside is still initializing. PostgreSQL may be performing recovery or running migrations; Kafka may not have created topics yet; an HTTP API may open port 8080 before loading configuration, caches, or baseline data.

If a test immediately calls the API as soon as the container begins accepting TCP connections, results easily become **flaky**: a fast developer machine passes while a slower CI runner returns HTTP 503 or connection timeouts. Adding `Thread.sleep(10000)` does not solve the real problem: sleeping long enough might still fall short on CI, while needlessly slowing down fast machines.

Testcontainers separates two core concepts:

- **Startup check strategy**: whether the container has reached the expected lifecycle state, such as a daemon staying running or a one-shot job exiting with 0.
- **Wait strategy**: whether the service inside the container is **usable for the test's objective** — e.g., a port is listening, HTTP `/ready` returns 200, logs report migrations completed, or Docker `HEALTHCHECK` reports healthy.

Once the wait succeeds, the test should still invoke a **real business operation** and assert its outcome. Readiness is only the starting gate, not proof that all business functions work properly.

### Learning objectives

1. Distinguish Docker running, socket listening, liveness, readiness, and business-level verification.
2. Understand `GenericContainer` defaults and the difference between startup checks and readiness waits.
3. Use `Wait.forListeningPort()`, `Wait.forHttp(...)`, `Wait.forLogMessage(...)`, `Wait.forHealthcheck()`, and `WaitAllStrategy`.
4. Choose the right status, path, body predicate, healthcheck, and startup timeout per backend.
5. Connect Spring Boot to Testcontainers' host/mapped port via `@DynamicPropertySource` or `@ServiceConnection`.
6. Know why Docker health states, logs, and port checks can sometimes give false signals.
7. Diagnose timeouts, container exits, startup failures, HTTP 401/503, wrong keyspaces/schemas, and context lifecycle caching.
8. Write a **deterministic** integration test proving an open port does not mean the service is ready, without using sleeps in tests.
9. Verify a real business HTTP operation after readiness is confirmed.
10. Know when to use one-shot startup checks, multi-container dependencies, Actuator liveness/readiness probes, and CI assertions on executed test counts.

This lesson uses **Java 17, Spring Boot 3.5.16, Testcontainers Java 1.21.x API, JUnit Jupiter, and Maven**. A simulated HTTP service runs inside a Python Docker image; the tests and Spring client are written in Java. The environment needs a Docker-compatible runtime and image pull access; Python does not need to be installed on the host.

## 2. Five states to keep distinct

~~~text
Docker CREATE
   |
   v
Process RUNNING (Docker inspect state)
   |
   v
Port LISTENING (TCP accept connection)
   |
   v
Application READY (GET /ready => 200 + READY)
   |
   v
Business USABLE (GET /api/orders/42 => 200 + expected data)
~~~

| Layer | Signal | Does not prove |
| --- | --- | --- |
| Container created | Docker container ID exists | Process is alive |
| Container running | Entrypoint process has not exited | TCP port is open |
| Port listening | TCP handshake succeeds | Schema/credentials/cache are ready |
| Liveness | `GET /live` reports process is healthy | Dependencies suffice to serve requests |
| Readiness | `GET /ready` reflects ability to accept requests | Every business rule works |
| Business probe | Calls real endpoint/query with specific assertions | System cannot fail later |

### 2.1. Liveness and readiness differ

Liveness answers: **is the process still alive, or does it need a restart?**

Readiness answers: **is the service currently fit to process requests within its defined scope?**

When a database is briefly down, an application may stay liveness `UP` while readiness is `DOWN`. Never turn every dependency outage into a liveness failure that triggers orchestrators to restart pods in a loop. Conversely, reporting readiness `UP` when a critical database or schema is unready is a false signal.

### 2.2. Readiness must have a clear contract

For example, an Order API needs:
- HTTP routes initialized.
- DB connection able to authenticate.
- Required migrations or schema versions applied.
- Needed indexes, tables, and permissions present.
- Essential internal state loaded.

If the API still serves core operations cleanly when an optional analytics backend fails, analytics should not block readiness. The health contract depends on requirements; there is no single universal dependency checklist for all apps.

### 2.3. Readiness is only a snapshot

Right after `container.start()`, a backend can still restart or lose connectivity. Readiness does not replace retries, error handling, or circuit breakers in real applications. Tests must still exercise real operations rather than assuming the wait strategy guarantees every future request.

### 2.4. Why include a negative example in tests?

If you only write `Wait.forHttp("/ready")` and the test passes, learners easily mistake it for a TCP port wait. The project in this lesson intentionally includes a **manual** mode: the port and `/live` work, yet `/ready` returns 503 until the test sends a command turning readiness on. That gives deterministic evidence independent of CI speed.

## 3. Startup check strategy vs wait strategy

### 3.1. Startup check

Testcontainers tracks container state via `StartupCheckStrategy`. By default, `IsRunningStartupCheckStrategy` fits long-lived daemons/services: the process counts as started when it is running and has not exited abnormally.

For a short-lived job, such as a migration:
- Exit **0** can signify success.
- Exit **1** is a failure.
- The process does not stay running forever or open a TCP port.

`OneShotStartupCheckStrategy` targets this kind of job; `IndefiniteWaitOneShotStartupCheckStrategy` is a variant without the same startup deadline. Use indefinite waits only when the job is supervised externally; a job hanging forever makes a poor integration test.

`MinimumDurationRunningStartupCheckStrategy` or `withMinimumRunningDuration(Duration...)` verifies the container remains running for a short interval, yet still **does not prove application readiness**.

### 3.2. Wait strategy

Once the container passes its startup check, Testcontainers uses a `WaitStrategy` to determine when the service is ready. For `GenericContainer`, Testcontainers Java documentation notes the default generally waits for **the first mapped port to start listening**, with a base wait timeout around 60 seconds.

~~~java
GenericContainer<?> nginx = new GenericContainer<>(
        DockerImageName.parse("nginx:1.27-alpine"))
        .withExposedPorts(80);
~~~

The snippet above is illustrative, not a standalone Java class. For Nginx serving static pages, a port wait may suffice. For an API running migrations, an open port comes too early.

### 3.3. Lifecycle when calling start()

~~~text
new GenericContainer(...) 
        |
        v
Docker pull/create/start
        |
        v
StartupCheckStrategy: running / one-shot exit?
        |
        v
WaitStrategy: port / HTTP / log / healthy?
        |
        v
Container.start() returns
        |
        v
Spring context / JUnit test uses service
        |
        v
Business assertions
~~~

Failure classification:
- **Process exits 1**: startup check failure; raising HTTP wait timeout will not fix an invalid command/config.
- **Process running, HTTP wait timeout**: not ready yet, wrong path/port, auth failure, hung service, or wrong wait predicate.
- **Wait succeeds, business GET fails**: overly weak readiness check or business/authorization/data/runtime bug after wait.

## 4. Common wait strategies

### 4.1. Wait.forListeningPort()

~~~java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.2-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
~~~

This is a test fixture snippet requiring Testcontainers imports. An open socket is a minimal signal; if tests need Redis to process commands, send `PING` or `SET`/`GET` via the client or command after start. For SQL databases, check SQL query/schema readiness whenever requirements go beyond raw TCP connectivity.

### 4.2. Wait.forHttp() for HTTP readiness

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("nginx:1.27-alpine"))
        .withExposedPorts(80)
        .waitingFor(Wait.forHttp("/")
                .forPort(80)
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofSeconds(60)));
~~~

In a real app, replace `/` with a meaningful readiness endpoint. Useful methods:
- `forPort(int)` picks the **container-internal port** mapped by Testcontainers.
- `forStatusCode(200)` requires a specific HTTP status.
- `forStatusCodeMatching(code -> code >= 200 && code < 300)` when the contract accepts a status range.
- `forResponsePredicate(body -> ...)` inspects the readiness payload, not just HTTP 200.
- `usingTls()` for HTTPS; `allowInsecure()` only for intentional test-only certificates.
- `withMethod("GET")`, `withHeader(...)`, `withBasicCredentials(...)` for endpoints with special requirements.
- `withReadTimeout(Duration...)` bounds each individual HTTP probe.
- `withStartupTimeout(Duration...)` bounds the total readiness wait window.

Important example:

~~~java
Wait.forHttp("/ready")
        .forPort(8080)
        .forStatusCode(200)
        .forResponsePredicate(body ->
                body.contains("\"status\":\"READY\""))
        .withStartupTimeout(Duration.ofSeconds(45));
~~~

If the endpoint returns 200 with body `{"status":"STARTING"}`, the body predicate prevents a false positive. When the endpoint returns 503 for not-ready, status checks handle the basic case, yet body assertions still protect the contract.

**Do not** casually accept 401/302 as success if downstream tests expect an authenticated API. Allow those statuses only when that matches the readiness contract and you pair it with a real business probe.

### 4.3. Wait.forLogMessage()

~~~java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.2-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forLogMessage(
                ".*Ready to accept connections.*\\n", 1));
~~~

Log waits match a regex and occurrence count. They help when a service lacks an HTTP readiness endpoint yet logs a line **after** initialization completes.

Pitfalls:
- Wording or log formatting can change between versions.
- "Starting server" does not mean "ready."
- Overly broad regexes can match an unintended line.
- Buffering can delay log flushing.
- A ready log line sometimes prints before permissions/indexes/configs finish initializing for specific operations.

Always follow a log wait with **a protocol command or business operation**.

### 4.4. Wait.forHealthcheck()

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("example/my-app:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHealthcheck());
~~~

Applies only when the image actually defines a Docker `HEALTHCHECK`. Without a healthcheck in the image, Docker has no meaningful healthy state to wait on. `Wait.forHealthcheck()` does not invent a health endpoint.

Illustrative Dockerfile for the lesson's HTTP service:

~~~dockerfile
FROM python:3.12-alpine
COPY ready_server.py /app/ready_server.py

HEALTHCHECK --interval=1s --timeout=2s \
  --start-period=2s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=1)"

CMD ["python", "-u", "/app/ready_server.py"]
~~~

`urlopen` raises `HTTPError` when `/ready` returns 503, causing the healthcheck command to exit non-zero. On 200, it exits 0. This Dockerfile is an **optional extension**, not a required file for the runnable lab: the lab uses a prebuilt Python image with HTTP/log waits.

### 4.5. WaitAllStrategy

When multiple signals are needed:

~~~java
WaitAllStrategy combined = new WaitAllStrategy()
        .withStrategy(Wait.forLogMessage(
                ".*SERVICE_READY.*\\n", 1))
        .withStrategy(Wait.forHttp("/ready")
                .forPort(8080)
                .forStatusCode(200))
        .withStartupTimeout(Duration.ofMinutes(2));

container.waitingFor(combined);
~~~

This snippet sits inside a class with `container` and Testcontainers imports. Combining a "migration done" log with HTTP readiness is valuable when each condition guards a different risk. Avoid stacking redundant waits or ungrounded nested timeouts.

### 4.6. Custom wait strategy

When a backend lacks a reliable endpoint, log, or `HEALTHCHECK`, you can probe the protocol directly with a client or subclass `AbstractWaitStrategy` and override `waitUntilReady()`. Custom strategies must be bounded, produce clear error diagnostics, preserve root causes, and avoid printing secrets. Check API compatibility across Testcontainers versions.

Dedicated modules already configure appropriate start checks; do not replace the default wait on `PostgreSQLContainer` or `KafkaContainer` with a weaker TCP check without understanding the module's semantics.

## 5. Choosing readiness by backend

| Service | Stronger signal than an open port | Post-start assertion |
| --- | --- | --- |
| HTTP API | `GET /ready` 200 with expected body | Business GET/POST, JSON/body/status |
| Spring Boot Actuator | `/actuator/health/readiness` when probes enabled | Business endpoint and DB/schema |
| PostgreSQL | Real connection/JDBC, schema migrations done | `SELECT 1`, query target tables |
| MySQL/MariaDB | Auth + SQL query, schema version | Query/insert isolated test record |
| Redis | `PING -> PONG` or specific command | `SET`/`GET` when testing cache behavior |
| Kafka | Metadata/topics/partitions ready | Publish/consume test message |
| RabbitMQ | Connection/channel/queue/permissions ready | Publish and consume |
| Elasticsearch | Cluster/index/alias ready | Search/index query with fixture |
| Cassandra | Session, datacenter, keyspace | Table/query by partition key |
| Couchbase | Cluster/bucket/services/index | KV + SQL++ query per requirement |
| S3-compatible service | Health or signed API request | Put/get test-only object |
| Migration one-shot job | Exit code 0 | Expected schema version/queries |

No readiness signal proves full production SLAs, failover, or distributed consistency. The closer test infrastructure gets to production, the more precisely assertions should verify the target contract.

## 6. Hands-on project — Spring Boot 3.5.16 + Java 17 + Testcontainers

### 6.1. Idea

We build a small HTTP service in Python running **inside Docker**. It exposes 4 endpoints:

| Endpoint | Right after port opens | Once ready |
| --- | --- | --- |
| `GET /live` | 200, `{"status":"UP"}` | 200 |
| `GET /ready` | 503, `{"status":"NOT_READY"}` | 200, `{"status":"READY"}` |
| `GET /api/orders/42` | 503 | 200, `{"id":"42","status":"AVAILABLE"}` |
| `POST /admin/ready` | Transitions to ready, HTTP 204 | Stays ready, HTTP 204 |

`READY_MODE=manual` lets only the test flip readiness via POST; thus the port-only test does not depend on wall-clock timing. `READY_MODE=auto` switches to ready after 2 seconds inside the service and logs `SERVICE_READY`. The Java tests never use `Thread.sleep`.

Three test classes:
- `PortIsNotReadinessTest`: TCP wait returns while readiness/business endpoints still return 503; POST turns ready on, then asserts 200.
- `HttpReadinessSpringBootTest`: HTTP wait + response predicate; wires the Spring Boot client via `@DynamicPropertySource`.
- `LogReadinessTest`: log wait followed by calling the business endpoint to confirm.

### 6.2. Directory structure

~~~text
testcontainers-readiness-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/readiness/
│   ├── ReadinessLabApplication.java
│   └── BackendClient.java
├── src/test/resources/ready_server.py
└── src/test/java/com/example/readiness/
    ├── TestServices.java
    ├── HttpProbe.java
    ├── PortIsNotReadinessTest.java
    ├── HttpReadinessSpringBootTest.java
    └── LogReadinessTest.java
~~~

Place every file at its exact path and package. Python does not need to be installed on the host; the Docker image includes Python. You need a Testcontainers-supported Docker daemon/remote runtime, JDK 17+, and Maven. CI must be able to pull or fetch the image from an internal cache.

### 6.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>testcontainers-readiness-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
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

The Spring Boot parent manages dependency versions, including Testcontainers for Boot 3.5. Do not mix Testcontainers 2.x modules into 1.x imports/code without verifying compatibility. The project omits the Spring Web starter because the HTTP client uses Java 17's `java.net.http.HttpClient`; the backend is a Python container rather than a Spring REST controller.

### 6.4. application.properties

`src/main/resources/application.properties`:

~~~properties
# Fallback when starting the application outside tests.
# No server runs on this port unless you start one yourself.
backend.base-url=http://127.0.0.1:9999
~~~

In the Spring Boot test, `@DynamicPropertySource` overrides `backend.base-url` with Testcontainers' mapped host/port rather than using the fallback.

### 6.5. ReadinessLabApplication.java

~~~java
package com.example.readiness;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReadinessLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadinessLabApplication.class, args);
    }
}
~~~

### 6.6. BackendClient.java

`src/main/java/com/example/readiness/BackendClient.java`:

~~~java
package com.example.readiness;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class BackendClient {

    private final String baseUrl;
    private final HttpClient http;

    public BackendClient(Environment environment) {
        this.baseUrl = environment.getRequiredProperty(
                "backend.base-url");
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    public String baseUrl() {
        return baseUrl;
    }

    public HttpResponse<String> readiness()
            throws IOException, InterruptedException {
        return get("/ready");
    }

    public String order42()
            throws IOException, InterruptedException {
        HttpResponse<String> result = get("/api/orders/42");
        if (result.statusCode() != 200) {
            throw new IllegalStateException(
                    "upstream status " + result.statusCode());
        }
        return result.body();
    }

    private HttpResponse<String> get(String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(baseUrl + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return http.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Explanation:
- The bean only sets up the HTTP client and **never calls the endpoint inside its constructor**.
- `Environment.getRequiredProperty` reads the configuration when the Spring context builds the bean.
- Request/connection timeouts are bounded so tests never hang forever.
- `order42()` checks HTTP status, and tests additionally assert that the body contains the expected ID/state.
- Production runtimes need retries, circuit breakers, tracing, and credential handling as required; readiness at startup does not guarantee upstream stays healthy forever.

### 6.7. ready_server.py

`src/test/resources/ready_server.py`:

~~~python
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

READY = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/live":
            self.respond(200, {"status": "UP"})
            return
        if self.path == "/ready":
            if READY.is_set():
                self.respond(200, {"status": "READY"})
            else:
                self.respond(503, {"status": "NOT_READY"})
            return
        if self.path == "/api/orders/42":
            if READY.is_set():
                self.respond(200, {
                    "id": "42", "status": "AVAILABLE"
                })
            else:
                self.respond(503, {
                    "error": "DEPENDENCY_NOT_READY"
                })
            return
        self.respond(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if self.path != "/admin/ready":
            self.respond(404, {"error": "NOT_FOUND"})
            return

        READY.set()
        print("SERVICE_READY", flush=True)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format_string, *args):
        # Reduce access logs in the lab.
        pass


def complete_initialization():
    delay = float(os.environ.get("READY_DELAY_SECONDS", "2"))
    time.sleep(delay)
    READY.set()
    print("SERVICE_READY", flush=True)


server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
mode = os.environ.get("READY_MODE", "auto")

if mode == "auto":
    threading.Thread(
        target=complete_initialization,
        daemon=True
    ).start()

print("LISTENING", flush=True)
server.serve_forever()
~~~

Characteristics:
- The HTTP socket binds **before** readiness turns UP.
- `READY_MODE=manual` guarantees `/ready` **always returns 503** until the admin POST, regardless of how fast or slow the container starts.
- `READY_MODE=auto` simulates initialization with a 2-second delay; Java wait strategies poll the real status without sleeping.
- `SERVICE_READY` prints only after `READY.set()`, serving as a log readiness signal.
- The 204 response has no body, matching HTTP semantics.
- `/admin/ready` is solely a test hook — **never expose such a bypass mechanism in production**.
- All payloads are synthetic JSON without credentials or production data.

### 6.8. TestServices.java

`src/test/java/com/example/readiness/TestServices.java`:

~~~java
package com.example.readiness;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

final class TestServices {

    static final int PORT = 8080;

    private TestServices() {
    }

    static GenericContainer<?> pythonService(String mode) {
        return new GenericContainer<>(
                DockerImageName.parse("python:3.12-alpine"))
                .withExposedPorts(PORT)
                .withCopyFileToContainer(
                        MountableFile.forClasspathResource(
                                "ready_server.py"),
                        "/app/ready_server.py")
                .withCommand(
                        "python", "-u", "/app/ready_server.py")
                .withEnv("READY_MODE", mode)
                .withEnv("READY_DELAY_SECONDS", "2");
    }
}
~~~

The factory returns a **fresh container descriptor** without starting it and without sharing a mutable static container across test classes. Each test picks its own wait strategy. `withExposedPorts(8080)` sets up host port mapping; it does not mean the host port is 8080.

Tag `python:3.12-alpine` fits a demo; CI should pin a vetted image digest/version when requiring reproducibility or preventing supply-chain drift.

### 6.9. HttpProbe.java

`src/test/java/com/example/readiness/HttpProbe.java`:

~~~java
package com.example.readiness;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.testcontainers.containers.GenericContainer;

final class HttpProbe {

    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    private HttpProbe() {
    }

    static HttpResponse<String> get(
            GenericContainer<?> container, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        url(container, path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    static HttpResponse<String> post(
            GenericContainer<?> container, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(
                        url(container, path))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    static URI url(
            GenericContainer<?> container, String path) {
        return URI.create(
                "http://" + container.getHost()
                        + ":" + container.getMappedPort(
                                TestServices.PORT)
                        + path);
    }
}
~~~

Calls `container.getHost()` and `getMappedPort(8080)` **after `container.start`**. Never hardcode `localhost:8080`: Docker Desktop, CI, remote Docker, or Docker-in-Docker can map to another host/port. When one container calls another on the same Docker network, use the network alias and **internal port**, never copying the host mapped port into a container-to-container URL.

### 6.10. PortIsNotReadinessTest.java

`src/test/java/com/example/readiness/PortIsNotReadinessTest.java`:

~~~java
package com.example.readiness;

import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class PortIsNotReadinessTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("manual")
                    .waitingFor(Wait.forListeningPort())
                    .withStartupTimeout(Duration.ofSeconds(45));

    @Test
    void openPortDoesNotMeanBusinessReady()
            throws Exception {
        HttpResponse<String> live =
                HttpProbe.get(backend, "/live");
        HttpResponse<String> before =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> unavailable =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(live.statusCode()).isEqualTo(200);
        assertThat(live.body())
                .contains("\"status\":\"UP\"");

        assertThat(before.statusCode()).isEqualTo(503);
        assertThat(before.body())
                .contains("\"status\":\"NOT_READY\"");
        assertThat(unavailable.statusCode())
                .isEqualTo(503);

        HttpResponse<String> activate =
                HttpProbe.post(backend, "/admin/ready");

        assertThat(activate.statusCode()).isEqualTo(204);

        HttpResponse<String> ready =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> business =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(ready.statusCode()).isEqualTo(200);
        assertThat(ready.body())
                .contains("\"status\":\"READY\"");
        assertThat(business.statusCode()).isEqualTo(200);
        assertThat(business.body())
                .contains("\"status\":\"AVAILABLE\"");
    }
}
~~~

This is the key demonstration test: `/ready=503` is **guaranteed** after the port wait because `READY_MODE=manual`, independent of timing. After the admin POST, the test verifies readiness and the business endpoint. There is no JUnit `Thread.sleep` or dependence on machine speed.

### 6.11. HttpReadinessSpringBootTest.java

`src/test/java/com/example/readiness/HttpReadinessSpringBootTest.java`:

~~~java
package com.example.readiness;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class HttpReadinessSpringBootTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("auto")
                    .waitingFor(Wait.forHttp("/ready")
                            .forPort(TestServices.PORT)
                            .forStatusCode(200)
                            .forResponsePredicate(body ->
                                    body.contains(
                                            "\"status\":\"READY\""))
                            .withReadTimeout(
                                    Duration.ofSeconds(3))
                            .withStartupTimeout(
                                    Duration.ofSeconds(45)));

    @DynamicPropertySource
    static void backendProperties(
            DynamicPropertyRegistry registry) {
        registry.add("backend.base-url",
                () -> "http://" + backend.getHost()
                        + ":" + backend.getMappedPort(
                                TestServices.PORT));
    }

    @Autowired
    BackendClient client;

    @Test
    void readinessWaitAllowsBusinessCall()
            throws Exception {
        assertThat(client.readiness().statusCode())
                .isEqualTo(200);

        String response = client.order42();

        assertThat(response).contains("\"id\":\"42\"");
        assertThat(response)
                .contains("\"status\":\"AVAILABLE\"");
    }

    @Test
    void springBeanUsesDynamicMappedAddress() {
        String expected = "http://" + backend.getHost()
                + ":" + backend.getMappedPort(
                        TestServices.PORT);

        assertThat(client.baseUrl()).isEqualTo(expected);
    }
}
~~~

Checkpoints:
- `@Container` manages the service inside the JUnit class.
- `@DynamicPropertySource` supplies the mapped host/port to the Spring bean when the test context initializes.
- `Wait.forHttp("/ready")` waits for HTTP 200 **and** a response containing `READY`.
- `BackendClient` calls the real business endpoint over HTTP without mocking backend responses.
- `withReadTimeout` bounds a single HTTP probe, whereas `withStartupTimeout` is the readiness waiting budget. Do not confuse the two timeouts.
- `@ServiceConnection` is unnecessary for this custom Python HTTP server because Boot has no built-in connection factory for an arbitrary custom service.
- If an application needs to import container configuration across multiple classes, pay attention to JUnit static container lifecycles and Spring TestContext caching; the lab keeps a single standalone Spring integration class.

### 6.12. LogReadinessTest.java

`src/test/java/com/example/readiness/LogReadinessTest.java`:

~~~java
package com.example.readiness;

import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
class LogReadinessTest {

    @Container
    static final GenericContainer<?> backend =
            TestServices.pythonService("auto")
                    .waitingFor(Wait.forLogMessage(
                            ".*SERVICE_READY.*\\n", 1))
                    .withStartupTimeout(Duration.ofSeconds(45));

    @Test
    void readinessLogMustBeFollowedByBusinessProbe()
            throws Exception {
        HttpResponse<String> ready =
                HttpProbe.get(backend, "/ready");
        HttpResponse<String> order =
                HttpProbe.get(backend, "/api/orders/42");

        assertThat(ready.statusCode()).isEqualTo(200);
        assertThat(order.statusCode()).isEqualTo(200);
        assertThat(order.body())
                .contains("\"status\":\"AVAILABLE\"");

        assertThat(backend.getLogs())
                .contains("SERVICE_READY");
    }
}
~~~

Waiting only for `LISTENING` would be too early; because the demo logs `SERVICE_READY` **after setting the ready state**, the log wait reflects a stronger condition. Still, the test executes real HTTP calls rather than treating a log line as absolute proof.

### 6.13. Running Maven

~~~bash
mvn -q clean test

mvn -q -Dtest=PortIsNotReadinessTest test
mvn -q -Dtest=HttpReadinessSpringBootTest test
mvn -q -Dtest=LogReadinessTest test
~~~

When Docker is available:
- The port test verifies 200 liveness / 503 readiness before admin POST, then 200 readiness/business after.
- The HTTP Spring test waits for service readiness, then verifies business JSON and mapped address.
- The log test waits for `SERVICE_READY`, then verifies HTTP status/payload.
- A successful Maven run exits with code 0; check executed test counts and reports in `target/surefire-reports`.

**Crucial:** `@Testcontainers(disabledWithoutDocker = true)` can **skip tests** when Docker is unavailable. Exit code 0 with skipped tests does not prove integration passed. In dedicated integration CI, require the Docker runtime and assert executed counts with `skipped=0`.

This sample source was reviewed against the Testcontainers 1.21.x API; Maven/Docker were not executed during authoring. Do not promise a fixed elapsed time or console output because image pulls, Docker hosts, JDK/Maven caches, and CI resources differ.

## 7. Spring Boot integration and service connections

### 7.1. @DynamicPropertySource for custom backends

`@DynamicPropertySource` registers suppliers producing properties on demand:

~~~java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("backend.base-url",
            () -> "http://" + backend.getHost() + ":"
                    + backend.getMappedPort(8080));
}
~~~

Requires `static GenericContainer<?> backend` on the same test class. Do not evaluate the mapped port before the container starts. Using dynamic host/port allows tests to work against remote Docker rather than hardcoded URLs.

### 7.2. @ServiceConnection with known containers

With Spring Boot 3.5 and `spring-boot-testcontainers`, many typed containers have factories generating connection details automatically. Example:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

This snippet is **not part of the runnable Python lab**; it needs Maven modules `spring-boot-testcontainers` and `org.testcontainers:postgresql`. When recognized, Spring Boot creates `JdbcConnectionDetails` (and other details where applicable) so auto-configured clients connect to the right container.

`@ServiceConnection` does **not**:
- Perform business schema migrations automatically.
- Provision Kafka topics, search indexes, or S3 buckets.
- Make readiness stronger than the container's wait strategy.
- Automatically turn a generic HTTP service into a recognized backend type.
- Guarantee external credentials or authorization succeed.

For a `GenericContainer` declared as a Spring `@Bean`, generating Redis-like connection details may require `@ServiceConnection(name="redis")` so Boot knows the image category. Custom HTTP services still use dynamic properties or custom connection details.

### 7.3. Static `@Container` and cached `ApplicationContext`

Spring Boot 3.5 documentation notes that JUnit `@Testcontainers` static fields normally stop after the test class finishes. Spring TestContext can cache `ApplicationContext` across classes; if a context is reused with a client pointing to a stopped container, later tests fail confusingly.

When multiple Spring test classes share dependencies, consider declaring **containers as Spring beans** in `@TestConfiguration`:
- Spring starts container beans before dependent beans.
- Spring destroys dependent beans before stopping container beans.
- Containers live alongside the cached context lifecycle.

Do not blindly place a static singleton container with `@Container`/`@Testcontainers` on every class assuming context caching will not interfere. For a single integration class like in this lab, a static container is simple and valid.

### 7.4. Networking in multi-container tests

When the test JVM calls container A, use:
- `container.getHost()`.
- `container.getMappedPort(internalPort)`.

When container A calls container B on the same `Network.newNetwork()`, use:
- `withNetworkAliases("database")`.
- `database:5432` or the matching internal port.

Never pass B's mapped host port as a container-to-container address unless your network architecture explicitly demands it. `dependsOn` sets startup ordering, yet B's readiness is only as strong as the wait strategy configured on B.

## 8. Timeouts and startup attempts

| Timeout | Scope | Guidance |
| --- | --- | --- |
| `WaitStrategy.withStartupTimeout` | Deadline for the ready condition to pass | Base on startup P95/P99 plus CI margin |
| `GenericContainer.withStartupTimeout` | Container startup/wait budget per API | Not the same as a single HTTP probe timeout |
| `HttpWaitStrategy.withReadTimeout` | Timeout for a single HTTP probe | Smaller than or proportional to total readiness budget |
| HTTP client connect timeout | TCP connect from test JVM | Never wait indefinitely |
| HTTP request timeout | One business request | Match test/operation SLA |
| JUnit `@Timeout` | Whole test method | Watch thread behavior with transactional tests |
| Docker image pull/build | Image acquisition | Not always included inside the HTTP readiness budget |

### 8.1. Do not raise timeouts indefinitely

If 60 seconds passes without readiness, check:
1. Is the container crashing or restarting?
2. Did the Docker daemon and image pull/build succeed?
3. Did the service bind `0.0.0.0` and the container internal port?
4. Does `/ready` return 404/401/503 or time out?
5. Are databases, users, schemas, credentials, or migrations missing?
6. Does the log regex match the exact version, newline, and buffering?
7. Is the healthcheck command installed inside the image with sufficient permissions?
8. Is CI starved of CPU/memory so initialization stalls?
9. Is startup legitimately slow, or genuinely deadlocked?

Raise timeouts only after observing a valid initialization process needing more time. Bumping timeouts to several minutes will not fix a wrong keyspace, port, or permission.

### 8.2. Startup attempts vs poll attempts

~~~java
container.withStartupAttempts(2);
~~~

Use this when there is a valid reason to retry **the entire container launch**. An HTTP wait strategy already polls readiness within one start; they are not the same thing. Retrying launches can mask configuration bugs, so always retain logs and root causes on failure.

### 8.3. Do not add extra sleeps after start()

Wrong:

~~~java
backend.start();
Thread.sleep(15000);
assertThat(client.fetch()).isNotNull();
~~~

If the backend is ready in 1 second, the test wastes 14 seconds; if it takes 20 seconds, the test still fails. Fix the readiness contract and wait strategy instead. For eventual consistency on search indexes or replicas, use **bounded polling at the business assertion itself**, rather than abusing startup waits for post-write behavior.

## 9. Spring Boot Actuator readiness probes

With `spring-boot-starter-actuator` and matching configuration:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

An application can expose `/actuator/health/readiness`. The endpoint, path, and management port can vary by configuration; verify against your actual setup. Custom `HealthIndicator` beans should ensure readiness reflects **critical** dependencies rather than merely an open web listener.

Testcontainers snippet:

~~~java
GenericContainer<?> app = new GenericContainer<>(
        DockerImageName.parse("example/orders-service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp(
                        "/actuator/health/readiness")
                .forPort(8080)
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
~~~

This snippet targets an Actuator-enabled image, **not** the Python lab. If readiness reports `DOWN`/`OUT_OF_SERVICE` with HTTP 503 during startup, the wait keeps polling; on 404 check endpoint exposure/context path; on 401 supply valid auth rather than accepting 401 as ready.

**Liveness is not readiness**: keep DB pings out of liveness so transient DB hiccups do not trigger restart loops; readiness can transition `DOWN` while the process stays alive to recover.

## 10. One-shot migration jobs

### 10.1. Daemons vs batch jobs

A database server is a daemon: the process is expected to stay running continuously. A container running a Flyway/CLI migration is **one-shot**: it succeeds when it exits 0 upon finishing. Under the default is-running startup check, a fast-exiting job would be flagged as a startup failure even though it behaved properly.

Testcontainers provides `OneShotStartupCheckStrategy` for this container type. Checking exit code 0 alone is insufficient when the business contract is schema mutation: afterward, run SQL/JDBC queries verifying schema version, tables, and indexes.

### 10.2. Why is a "migrations complete" log line insufficient?

A migration job can print a step-completed message and still fail at commit or in a later step. Verify exit code 0 and check database state with real transactions/queries. On failure, surface logs instead of setting `Wait.forLogMessage(".*Migration.*")` and calling it done.

### 10.3. When an app depends on a migration job

Ensure the migration job completes before the application is considered ready. If using Testcontainers `dependsOn`, the dependency must have an appropriate startup check/wait contract itself. Never treat an open database port as proof that migrations finished.

## 11. How to verify a service is **truly** usable

### 11.1. A readiness endpoint can still lie

A `/ready` endpoint returning 200 just because the JVM booted can miss problems such as:
- The app points to the wrong database, tenant, or schema.
- Required topics have not been provisioned.
- Credentials allow connecting yet lack query/insert privileges.
- Search indexes are unbuilt even though cluster HTTP responds.
- Cache warmup has not finished while endpoints rely on the cache.

So after `start()`, invoke an operation representing the contract:
- JDBC: `SELECT 1` and query target tables/schemas.
- Redis: `PING`, or `SET`/`GET` on a test key.
- Kafka: topic metadata, publish + consume a test message.
- HTTP: real route, status, JSON/headers response.
- Search: index, query, expected result.

### 11.2. Business assertions should inspect the body too

Checking only HTTP 200 lets a proxy or default landing page return HTML 200 and pass. The lab asserts `"id":"42"` and `"status":"AVAILABLE"` to verify routing and minimal logic, not just an open port or homepage.

### 11.3. Readiness can change after startup

A backend can be healthy during the probe and fail moments later. Production clients must handle runtime failures. Testcontainers provides no permanent availability guarantee; in tests, distinguish startup races from intentional resilience fault-injection scenarios.

### 11.4. Never cause production side effects with readiness probes

Readiness should be idempotent and lightweight. When a business probe performs `INSERT`/`POST`, target a test-only namespace, synthetic identity, or ephemeral/cleaned database. Never probe by placing real orders or hitting real payment providers every second.

## 12. Troubleshooting by failure category

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Docker not detected | Docker daemon/permissions/remote context | Check Docker runtime and Testcontainers environment |
| Image pull fails | Registry/auth/network/nonexistent tag | Pin image and verify registry credentials |
| Process exits 1 | Invalid command/config/credentials | Inspect startup logs, entrypoint, env vars |
| TCP wait timeout | Wrong interface/port binding | `withExposedPorts`, bind `0.0.0.0` |
| TCP passes, HTTP 503 | Service still initializing | `Wait.forHttp("/ready")` matching contract |
| HTTP 404 | Wrong context path/endpoint | Check routes and Actuator exposure |
| HTTP 401/403 | Readiness endpoint requires auth | Supply headers/basic auth or adjust readiness policy |
| HTTP 200 yet body mismatch | Response not `READY` yet | `forResponsePredicate` matching ready payload |
| Log wait never finishes | Wrong regex, unbuffered/unflushed log, changed wording | Inspect raw logs and newline in regex |
| `HEALTHCHECK` stays unhealthy | Broken Dockerfile health command or unready service | `docker inspect` health state and logs |
| Test passes then business call fails | Weak readiness or wrong data | Verify business queries, credentials, and schema |
| Docker tests skipped | `disabledWithoutDocker=true` | Require executed tests in CI; never equate skip with PASS |
| Context cached yet container stopped | JUnit/Spring lifecycle mismatch | Spring-managed container bean or context isolation |
| Flakes in CI while local always passes | Timing/CPU/memory/parallelism | Record startup progression, readiness polls, and logs |
| Container running yet hits wrong tenant | Wrong namespace/schema/bucket config | Assert identifier and run real queries |
| One-shot exits 0 yet wait fails | Using daemon startup check on a batch job | Use one-shot strategy and verify side effects |

### 12.1. Reading logs and error causes

~~~java
String output = backend.getLogs();
System.out.println(output);
~~~

This snippet is strictly for debugging: logs may hold credentials/PII so scrub or limit output. Keep the `ContainerLaunchException` cause and trailing HTTP readiness response when possible.

Docker CLI while the container still exists:

~~~bash
docker ps -a
docker logs <container-id>
docker inspect <container-id>
~~~

Here `<container-id>` is a placeholder for the actual ID. Testcontainers may stop/remove containers at the end of a class; when no container remains to inspect, rely on logs captured inside the test or run a targeted debug session.

### 12.2. Protocol-level Redis check

~~~java
Container.ExecResult ping =
        redis.execInContainer("redis-cli", "PING");

assertThat(ping.getExitCode()).isZero();
assertThat(ping.getStdout().trim()).isEqualTo("PONG");
~~~

This snippet requires a Redis container, imports, and AssertJ; it is not part of the runnable lab. Since the command runs **inside** the container, it does not prove host-to-container networking works; when networking is part of the contract, add a check from the real test JVM client.

### 12.3. If the readiness contract is wrong, do not patch it with sleep

A `/ready` endpoint hardcoded to always return 200 during migrations must be fixed in the application. If a "started" log line fires before readiness, wait for the real ready log or use a stronger probe. Huge timeouts and infinite retries only mask bugs and slow down CI.

## 13. Anti-patterns to avoid

### 13.1. Waiting on TCP for an API running migrations

Port 8080 can accept connections before business endpoints are usable. Wait on `/ready` or a query/schema check.

### 13.2. Treating `/live` as `/ready`

Liveness `UP` does not prove dependencies are available. Keep the two endpoints distinct.

### 13.3. Accepting HTTP 200 regardless of body

If a service returns 200 with `STARTING`, use `forResponsePredicate` to inspect the payload status.

### 13.4. Log regex matching only "Starting"

Wait for "Ready" after initialization rather than "Starting," and still verify a real business operation.

### 13.5. `HEALTHCHECK` missing from the image

`Wait.forHealthcheck()` requires an actual Docker `HEALTHCHECK`; it does not infer one from an HTTP endpoint.

### 13.6. Calling `localhost:8080` from the host JVM

Docker maps ports dynamically. Use `getHost()` and `getMappedPort`.

### 13.7. Using a host mapped port between two containers

On the same Docker network, use the network alias and internal port to avoid misaddressing.

### 13.8. Fixed sleep after `start()`

Sleep does not mean readiness and makes tests slow and flaky. Wait on conditions instead.

### 13.9. Treating `@ServiceConnection` as a migration tool

Valid connection details do not mean schemas, indexes, or topics exist.

### 13.10. Accepting every HTTP status as ready

HTTP 401/302 can indicate authentication/redirect bugs; accept them only if explicitly required by contract.

### 13.11. Mixing `@Container` and cached Spring contexts carelessly

A cached context can retain clients pointing to a stopped container. Prefer Spring-managed container lifecycles.

### 13.12. Skipping Docker tests while reporting integration PASS

Skipped test status is not test success. CI must check actual executed test counts.

### 13.13. Treating one-shot exit 0 as a daemon crash

Use the proper startup check strategy for jobs, then verify exit code and effects.

### 13.14. Coupling readiness too tightly to optional systems

When degraded mode is supported, the readiness contract should reflect critical capabilities rather than cascading failures from optional dependencies.

### 13.15. Checking endpoints without checking business output

Wait strategies are only the first step; add real GET/SQL/protocol assertions.

## 14. Exercises

1. Run `PortIsNotReadinessTest` and explain why the port is open while `/ready=503`.
2. Replace `Wait.forListeningPort()` with `Wait.forHttp("/ready")` in manual mode without calling admin; observe the intentional startup timeout.
3. Use auto mode so the HTTP wait receives 200/READY after initialization.
4. Configure a body predicate expecting `NEVER_READY` and inspect the timeout failure.
5. Change the log wait to match only `LISTENING`; explain why it is weaker than `SERVICE_READY`.
6. Add `GET /api/orders/99` returning different data and assert its exact ID and status.
7. Use `@DynamicPropertySource` and assert the Spring bean receives the real mapped host/port.
8. Add a Dockerfile `HEALTHCHECK` probing `/ready` and test `Wait.forHealthcheck()`.
9. Combine log and HTTP checks in `WaitAllStrategy`, and analyze timeouts when one signal fails.
10. Start a Redis container and execute `redis-cli PING` after the port wait.
11. Use `PostgreSQLContainer`, run migrations, and query a real table to prove JDBC readiness is not schema readiness.
12. Simulate a one-shot migration exiting 0 and verify the schema, plus a case exiting 1.
13. With Spring Actuator, expose `/actuator/health/readiness` and configure an exact HTTP wait.
14. Hardcode port 8080 and run against Docker Desktop / a remote runner to observe why it fails.
15. Inspect Surefire reports with Docker stopped: distinguish skipped integration tests from PASS.
16. Set up two `@SpringBootTest` classes sharing one container and evaluate context caching and lifecycle.
17. Protect the readiness endpoint with auth, observe 401, and prove it works only with valid credentials.
18. Define P95/P99 startup budgets and choose a grounded `withStartupTimeout`.
19. For container-to-container communication, configure a `Network` alias and switch from mapped host port to internal port.
20. Add a business assertion after readiness to catch a wrong schema/namespace even when the health endpoint reports UP.

## 15. Pre-merge checklist

- [ ] Distinguished Docker created/running, TCP listening, and application readiness?
- [ ] `StartupCheckStrategy` matches daemon vs one-shot job?
- [ ] Wait strategy is strong enough for the operation under test?
- [ ] Liveness and readiness are not confused?
- [ ] HTTP wait checks port/path/status/body as needed?
- [ ] `Thread.sleep` is never used as a readiness condition?
- [ ] Log regex matches post-init "ready," not just "starting"?
- [ ] Docker image defines a `HEALTHCHECK` before using `Wait.forHealthcheck`?
- [ ] Connect/read/wait/test timeouts are all bounded and reasonable?
- [ ] Timeouts were not raised blindly to hide config bugs?
- [ ] Host and mapped port come from Testcontainers?
- [ ] Network alias/internal port used properly for container-to-container calls?
- [ ] Business-level smoke check runs after `container.start()`?
- [ ] Schemas/indexes/topics/seed data are genuinely ready?
- [ ] Spring Boot `@DynamicPropertySource`/`@ServiceConnection` applied properly?
- [ ] Container lifecycle fits Spring context caching?
- [ ] Docker CI image versions/resources/permissions are managed?
- [ ] No production credentials, data, or external side effects?
- [ ] Logs/causes/health status captured for timeout diagnostics?
- [ ] CI never treats skipped Docker tests as an integration PASS?
- [ ] README code and Maven commands verified in the build pipeline?

**Conclusion:** Container `RUNNING`, port `LISTENING`, and service `READY` are three separate states. Startup checks govern lifecycle, while wait strategies check usability. For slow-initializing HTTP APIs, wait on `/ready` with the right status/payload, a reliable readiness log, or Docker `HEALTHCHECK`; then execute a real business request. Connect Spring Boot via dynamic mapped addresses, align container lifecycles, and keep timeouts bounded so integration tests stay fast, stable, and diagnostic.

## 16. References

- Testcontainers Java — Startup and Wait Strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers Java — JUnit Jupiter quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers Java — Manual container lifecycle: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/
- Testcontainers Java 1.21.x — HttpWaitStrategy API: https://javadoc.io/static/org.testcontainers/testcontainers/1.21.4/org/testcontainers/containers/wait/strategy/HttpWaitStrategy.html
- Testcontainers Java 1.21.x — WaitAllStrategy API: https://javadoc.io/static/org.testcontainers/testcontainers/1.21.4/org/testcontainers/containers/wait/strategy/WaitAllStrategy.html
- Spring Boot 3.5 — Testcontainers, Service Connections and bean lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Actuator endpoints and Kubernetes probes: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Docker — Dockerfile HEALTHCHECK: https://docs.docker.com/reference/dockerfile/#healthcheck
- Docker — Testcontainers lifecycle for Java: https://docs.docker.com/guides/testcontainers-java-lifecycle/
