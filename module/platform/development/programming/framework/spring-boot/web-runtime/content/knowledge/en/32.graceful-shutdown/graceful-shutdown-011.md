# Verifying Zero Lost Requests During Spring Boot Version Rollouts

## 1. Purpose and meaning of “zero lost requests”

A Spring Boot system serving continuous traffic needs to gradually replace version v1 with v2 without dropping active transactions. This process is typically called a rolling deployment or rolling update. Even when Kubernetes reports that the Deployment rollout succeeded and new Pods are Ready, that **does not by itself prove** every user HTTP request completed.

Typical failure points:

- A client opens a connection to Pod v1 right before the load balancer updates terminating endpoints.
- Pod v1 is processing a 5-second HTTP request and gets SIGKILLed before returning the response.
- A POST committed to the DB, yet the TCP connection closed before HTTP 201 reached the client.
- The client retries the POST, creating two orders because idempotency is missing.
- A worker ACKed a message before committing business state; the Pod is replaced and the message is never reprocessed.
- Long-lived hours-long SSE, WebSocket, or gRPC streams are severed when old Pods stop.
- v2 reports Ready while database migrations or shared-session formats are incompatible with v1.

Therefore, distinguish at least four distinct goals:

| Goal | Evidence required | Insufficient to prove |
| --- | --- | --- |
| **Continuous availability** | Instances have enough capacity and Ready endpoints throughout rollout | Merely seeing `replicas=3` |
| **HTTP completion** | Clients receive successful responses or failed requests are identified | Server received the request |
| **Eventual success** | Every logical request ID completes within allowed retries and SLO | Running a single `cURL 200` |
| **Durable business correctness** | Every accepted operation is durably recorded; zero duplicate effects | Merely turning on graceful shutdown |

Clearly distinguish two different criteria:

1. **Zero transient errors:** clients never see 502, 503, timeouts, or connection resets even without retries. Very hard to guarantee absolutely over distributed networks.
2. **Zero lost logical operations:** requests may need retries/reconciliation, yet none are lost and none cause duplicate effects. Requires idempotency, durable storage, and verification.

Zero loss cannot be promised across all node crashes, OOMs, network partitions, client timeouts, and external payment systems. Yet you can build **strong evidence for a specific SLO**, verified per layer, per request ID, and against durable business state.

## 2. Two data paths to verify

~~~text
Client / Synthetic test
          |
          v
Ingress / Reverse proxy / API gateway
          |
          v
Kubernetes Service / EndpointSlice
          |
    +-----+------+
    |            |
    v            v
 Spring v1    Spring v2
   (old)        (new)
    |            |
    +------+-----+
           |
           v
       DB / broker
           |
           v
   Business effect durable
~~~

**Orchestration path:** does routing move new requests off the terminating Pod in time? Are any requests still routed to the old IP after Spring stops accepting connections?

**Business path:** do already-accepted requests finish during the graceful window? If the app committed yet the response was lost, can clients safely query status or retry? If a worker is killed, is the message reprocessed and is its side effect idempotent?

Spring Boot mainly handles HTTP processing and Pod lifecycle. Kubernetes/LB handle traffic routing. Databases and brokers decide durability; clients govern retries/reconnects. **A single flag cannot replace all four parts.**

## 3. Timeline of a rolling update and shutdown

~~~text
T0  v1 Pods Ready, serving traffic
T1  Deployment creates an additional v2 Pod per maxSurge
T2  v2 starts up; liveness may be UP, readiness not Ready yet
T3  v2 Ready, EndpointSlice/LB begins routing traffic
T4  Controller selects old v1 Pod for deletion
T5  EndpointSlice marks Pod terminating, ready=false
T6  LB/gateway gradually drops old backend from new traffic
T7  preStop hook runs if configured, within grace period
T8  SIGTERM is sent to the Java process
T9  Spring ApplicationContext closes, graceful shutdown begins
T10 HTTP listener refuses new requests, waits for in-flight requests
T11 Process exits cleanly, Pod is deleted
T12 Repeats until all Pods are v2
~~~

Between T5 and T6 lies a **propagation delay**: EndpointSlices, kube-proxy, ingress controllers, and cloud load balancers do not update simultaneously on a single clock. HTTP keep-alive can also reuse old connections.

In Kubernetes, a terminating endpoint carries condition `ready=false` to exclude it from regular traffic, while `serving` can reflect that it still serves existing connections. That provides a draining mechanism, **yet does not confirm every external LB respects it instantaneously**.

**Observations needed:** timestamp of the last request routed to Pod v1, when Pod entered terminating, when SIGTERM was sent, how many in-flight requests completed before process exit, and ingress 502/503/EOF counts.

## 4. Spring Boot 3.3 graceful shutdown

For Spring Boot 3.3.x, Java 17+:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Graceful shutdown is supported by Tomcat, Jetty, Undertow, and Reactor Netty in Servlet MVC or reactive WebFlux. It runs when Spring `ApplicationContext` closes. The server stops new requests and gives existing requests time to finish.

Per **Spring Boot 3.3** docs:

- Tomcat, Jetty, and Reactor Netty stop accepting new requests at the network layer.
- Undertow may accept new connections and immediately return HTTP **503 Service Unavailable**.
- HTTP persistent connections and HTTP/2 can affect how new requests are rejected.
- Grace periods cannot be infinite; once the timeout expires, lifecycle shutdown phases proceed.

**Do not confuse** `spring.lifecycle.timeout-per-shutdown-phase` with total runtime shutdown timeout. It is the per-phase Spring lifecycle timeout, and the JVM may have other resources to stop. Kubernetes termination grace must budget enough for `preStop`, Spring phases, logging/cleanup, and a measured buffer.

Nor should you project newer Spring Boot defaults onto Boot 3.3. In this lesson, `server.shutdown=graceful` is declared **explicitly**.

### What Spring does not guarantee on its own

- Under SIGKILL/OOM/node loss, Java shutdown hooks never run.
- Kubernetes LB never routes a new request to the old Pod after SIGTERM.
- An `@Async` task is automatically awaited and durably persisted.
- Infinite SSE/WebSocket streams seamlessly migrate to another Pod.
- HTTP 200 was definitely received by the client.
- POST retries are safe without duplicate side effects.
- v1 and v2 can concurrently read/write the DB/schema/sessions.
- Message consumers never ACK before business COMMIT.

Graceful shutdown is a **foundation**, not an end-to-end exactly-once guarantee.

## 5. Kubernetes termination grace and preStop

Example lab budget:

~~~text
terminationGracePeriodSeconds = 50s
preStop sleep                =  8s
Spring graceful phase        = 25s
Other cleanup + margin       = 17s
~~~

`preStop` runs **before** kubelet sends TERM to the container and still counts toward `terminationGracePeriodSeconds`. If the hook takes 40 seconds out of a 45-second total grace, Spring can be killed as soon as it starts stopping. Kubelet sends a forcible kill when grace expires without adding `preStop` time on top.

A `preStop sleep 8` can give EndpointSlices/LBs time to learn the Pod is terminating while the app still accepts/handles valid requests. Yet **sleep 8 is not proof** propagation finished; measure on your real ingress/cluster. If your infrastructure has strong terminating-endpoint draining, a sleeping preStop may be unnecessary.

Note: shell-based hooks require a shell/`sleep` inside the image. Distroless containers usually lack them, causing hooks to fail. Hooks should be short, idempotent if invoked again in rare edge cases, and never open an unprotected public drain endpoint.

## 6. Readiness, liveness, and startup are not the same probe

- **Readiness:** Is the Pod ready to receive *new traffic*? When unready, Services should not route regular traffic to it.
- **Liveness:** Can the Pod still recover, or must it restart? Do not restart all Pods when a shared DB temporarily errors.
- **Startup:** Wait for a slow-starting app without premature kills from the liveness probe.
- **Terminating endpoint:** Even if previously Ready, the Pod is marked terminating so load balancers stop sending new requests.

Spring Boot Actuator supports health groups:

~~~text
GET /actuator/health/readiness
GET /actuator/health/liveness
~~~

Once the Spring Boot app is Ready, readiness normally returns HTTP 200 and `"status":"UP"`. During startup or draining, states can change or the HTTP listener may stop serving probes; do not look at raw status alone and assume all stages are synchronized.

If the management server uses a **different port** from the HTTP app, the management port may stay healthy even when the main HTTP listener failed. The example below runs Actuator on the same port 8080. Production should consider probes on the main port, restrict network exposure, and keep secrets out of Actuator.

## 7. Runnable Java 17+ project to measure in-flight HTTP

We build a small Spring MVC app with:

- `GET /work/{id}`: a read request holding the handler for 350–5000 ms and echoing request ID + revision + node.
- `GET /state`: revision, node, and in-flight counter of the **current JVM**.
- Actuator readiness/liveness.
- Spring graceful shutdown upon SIGTERM.

This is a lab testing **HTTP drainage**. An in-memory counter is not a durable ledger, and GET endpoints do not simulate business COMMITs. Durability patterns are covered later.

### 7.1. Structure

~~~text
rollout-verifier/
├── settings.gradle
├── build.gradle
├── Dockerfile
└── src/
    ├── main/
    │   ├── java/demo/rollout/RolloutVerifierApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/rollout/RolloutVerifierTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'rollout-verifier'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info,metrics

app.revision=${APP_REVISION:local}
~~~

Do not enable `management.endpoint.shutdown.enabled=true` just to test SIGTERM; the Actuator shutdown endpoint rarely needs public exposure and introduces security risks.

### 7.2. Java main + controller

`src/main/java/demo/rollout/RolloutVerifierApplication.java`:

~~~java
package demo.rollout;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class RolloutVerifierApplication {
    public static void main(String[] args) {
        SpringApplication.run(RolloutVerifierApplication.class, args);
    }
}

@RestController
class RolloutController {
    private final AtomicInteger inFlight = new AtomicInteger();
    private final String revision;
    private final String node;

    RolloutController(@Value("${app.revision:local}") String revision) {
        this.revision = revision;
        this.node = System.getenv().getOrDefault("HOSTNAME", "local");
    }

    @GetMapping("/state")
    Map<String, Object> state() {
        return Map.of(
                "revision", revision,
                "node", node,
                "inFlight", inFlight.get());
    }

    @GetMapping(value = "/work/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String work(@PathVariable long id,
                @RequestParam(defaultValue = "350") int delayMs)
            throws InterruptedException {

        if (id < 1 || delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "invalid request parameters");
        }

        inFlight.incrementAndGet();
        try {
            // LAB: hold the request thread for the specified duration.
            Thread.sleep(delayMs);
            return "id=" + id
                    + "|revision=" + revision
                    + "|node=" + node;
        } finally {
            inFlight.decrementAndGet();
        }
    }
}
~~~

**How to read results:**

- `id` is a synthetic client-generated ID used to track each request. Never put PII/tokens into URL paths in production.
- `revision` comes from `APP_REVISION`, showing whether v1 or v2 handled the request.
- `node` comes from Kubernetes `HOSTNAME` to identify the Pod.
- `inFlight` increments on controller entry and decrements when processing ends; it **does not prove the response traversed the network to the client**.
- `Thread.sleep` here only simulates synchronous work, not a production endpoint pattern.
- Never use an in-memory `inFlight` counter to reconcile business transactions after a Pod is killed.

### 7.3. JUnit HTTP integration tests

`src/test/java/demo/rollout/RolloutVerifierTest.java`:

~~~java
package demo.rollout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RolloutVerifierTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void workEchoesRequestId() {
        ResponseEntity<String> response = http.getForEntity(
                "/work/42?delayMs=1", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .startsWith("id=42|revision=");
    }

    @Test
    void invalidDelayReturns400() {
        ResponseEntity<String> response = http.getForEntity(
                "/work/42?delayMs=9000", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void stateHasInFlightCounter() {
        ResponseEntity<String> response = http.getForEntity(
                "/state", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("inFlight");
    }
}
~~~

Run with Java 17 and Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootJar
~~~

PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootJar
~~~

If the wrapper is missing, generate it with a compatible Gradle version or run installed Gradle. These tests verify HTTP routing; **they do not test rollouts, LBs, SIGTERM, or durable side effects**.

## 8. Testing SIGTERM while an HTTP request is still processing

Run the JAR:

~~~bash
APP_REVISION=v1 java -jar build/libs/rollout-verifier-1.0.0.jar
~~~

Another terminal:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/state
~~~

Then start a 5-second request:

~~~bash
curl -i "http://localhost:8080/work/42?delayMs=5000"
~~~

While it is running, send **SIGTERM** to the exact Java PID (Linux: `kill -TERM PID`). If SIGTERM arrives **after `/work/42` entered the controller**, Spring graceful shutdown has a chance to keep that request until it returns 200 within 25 seconds, then stops the listener/process.

**Repeat twice:** once sending SIGTERM after seeing the request in-flight; once sending SIGTERM before the request reaches the controller. In the second run, the new request can be rejected, which is a different case from losing an already-running request.

Never use `kill -9` to test graceful shutdown: SIGKILL skips Java shutdown hooks. Some IDE Stop buttons fail to send proper SIGTERM; use shell/container runtimes. If the client sees TCP reset, verify via request ID + timestamps/metrics whether the request was actually dispatched before SIGTERM.

### Verification means more than “the server shut down cleanly”

Even when the app logs “graceful shutdown complete”, an HTTP request that COMMITTED before losing its response can still make the client retry. For read-only GETs here, retrying is safe. For POSTs with side effects, use the mechanisms in section 12.

## 9. Docker ENTRYPOINT and SIGTERM delivery

`Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY build/libs/rollout-verifier-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Build/run:

~~~bash
docker build -t rollout-verifier:v1 .
docker run --rm --name rollout-old \
  -e APP_REVISION=v1 -p 8080:8080 rollout-verifier:v1
~~~

Send stop request:

~~~bash
docker stop --time 40 rollout-old
~~~

Exec-form ENTRYPOINT lets Java receive the stop signal directly. Using a shell wrapper `sh -c java ...` without `exec`/proper signal forwarding can prevent Java from receiving SIGTERM in time to run graceful shutdown. `docker stop --time 40` is a Docker CLI timeout example, not Kubernetes `terminationGracePeriodSeconds`.

Production projects must verify actual container image/runtime signal handling and shutdown logs, rather than merely reading the Dockerfile.

## 10. Sample Kubernetes Deployment + Service

The manifest below assumes the cluster already has image `rollout-verifier:v1` (pushed to a registry or loaded onto kind/minikube nodes). It does not build the image itself; use the Dockerfile above to create the image. File `k8s-rollout.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rollout-verifier
spec:
  replicas: 3
  minReadySeconds: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: rollout-verifier
  template:
    metadata:
      labels:
        app: rollout-verifier
    spec:
      terminationGracePeriodSeconds: 50
      containers:
        - name: app
          image: rollout-verifier:v1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: APP_REVISION
              value: "v1"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 8"]
---
apiVersion: v1
kind: Service
metadata:
  name: rollout-verifier
spec:
  selector:
    app: rollout-verifier
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### Why each setting was chosen

| Setting | Goal | Limitation |
| --- | --- | --- |
| `replicas: 3` | Keeps multiple backends during replacement | Does not guarantee each Pod has enough capacity |
| `maxSurge: 1` | Spawns one new Pod above desired count | Cluster must have spare CPU/RAM and DB pool capacity |
| `maxUnavailable: 0` | Avoids dropping Available Pods below desired during standard rollout | Does not guarantee zero 502s from network races |
| `minReadySeconds: 5` | New Pod stays Ready stably before counting as Available | Does not verify warm caches or API contracts |
| `readinessProbe` | Gates new requests by readiness state | Kubelet/EndpointSlice/ingress propagation is not instant |
| `livenessProbe` | Restarts broken processes | Never use shared DB outages to restart the whole fleet |
| `startupProbe` | Stops liveness from killing slow-starting apps | Does not replace readiness once started |
| `terminationGracePeriodSeconds: 50` | Total time before forcible kill | Includes preStop and shutdown |
| `preStop sleep 8` | Waits for LB to notice terminating before SIGTERM | Must be measured; not every LB needs 8s |
| `imagePullPolicy: IfNotPresent` | Works with images loaded onto local nodes | Production should use immutable digests/registries |

**Do not put a shell preStop on a distroless image** lacking `/bin/sh` or `sleep`. If your environment supports terminating-aware EndpointSlice draining well, the sleeping preStop can be omitted. Never copy lab durations blindly into production if SLOs/request durations differ.

### Running the rollout

~~~bash
kubectl apply -f k8s-rollout.yaml
kubectl rollout status deployment/rollout-verifier --timeout=180s
kubectl get pods -l app=rollout-verifier -o wide
kubectl get endpointslice \
  -l kubernetes.io/service-name=rollout-verifier
~~~

Build/publish/load image `v2`. In the **same manifest**, change `image: rollout-verifier:v1` to `image: rollout-verifier:v2`, and `APP_REVISION` from `v1` to `v2`. Then:

~~~bash
kubectl apply -f k8s-rollout.yaml
kubectl rollout status deployment/rollout-verifier --timeout=180s
kubectl rollout history deployment/rollout-verifier
~~~

**Load must run before and during applying v2.** If your test client only runs after the rollout succeeds, it fails to measure the drain transition.

Watching EndpointSlice changes and Pod termination reasons reveals the window where traffic might still hit the old Pod. Run `kubectl get pods -w` and capture ingress logs over the same window.

### Service DNS and the port-forward trap

`kubectl port-forward service/rollout-verifier 8080:80` is handy for debugging yet typically forwards to **one selected Pod**, bypassing the Service load-balancing path. Never use `port-forward` results as proof that the LB distributes requests across v1/v2.

To verify properly:
- From a test Pod inside the cluster, call `http://rollout-verifier.default.svc.cluster.local` when the namespace is `default`.
- Or use your system's real staging ingress hostname.
- Also compare public edge traffic when external infra uses caches/L7 connection pools.

HTTP keep-alive can pin a connection to an old backend, so measure multi-connection concurrency, per-node response fields, and ingress upstream routes.

## 11. Java 17 load generator tracking every request ID

Standalone program `RolloutProbe.java` runs outside Spring Boot with no external libraries. It sends a requested count of GET requests with bounded parallelism, retries HTTP/connection failures with bounded exponential backoff, and prints succeeded IDs, missing IDs, retried IDs, and responses by revision.

**GET `/work` is read-only**, making retries suitable in the lab. Never copy this retry loop blindly onto order/payment POSTs without idempotency keys.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RolloutProbe {
    record Outcome(
            int id, boolean success, int attempts,
            String revision, String detail) { }

    static Outcome call(HttpClient client, String base, int id)
            throws InterruptedException {

        String lastError = "not-started";

        for (int attempt = 1; attempt <= 5; attempt++) {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/work/" + id
                            + "?delayMs=350"))
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();

            try {
                HttpResponse<String> resp = client.send(
                        req, HttpResponse.BodyHandlers.ofString());

                if (resp.statusCode() == 200
                        && resp.body().startsWith("id=" + id + "|")) {
                    String revision = "unknown";
                    for (String part : resp.body().split("\\|")) {
                        if (part.startsWith("revision=")) {
                            revision = part.substring("revision=".length());
                        }
                    }

                    return new Outcome(
                            id, true, attempt, revision, "HTTP 200");
                }

                lastError = "HTTP " + resp.statusCode();
            } catch (IOException networkFailure) {
                lastError = networkFailure.getClass().getSimpleName();
            }

            if (attempt < 5) {
                long backoff = Math.min(1600L, 100L << (attempt - 1));
                Thread.sleep(backoff);
            }
        }

        return new Outcome(id, false, 5, "none", lastError);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java RolloutProbe.java BASE_URL COUNT PARALLEL");
            System.exit(2);
        }

        String base = args[0].replaceAll("/+$", "");
        int count = Integer.parseInt(args[1]);
        int parallel = Integer.parseInt(args[2]);

        if (count < 1 || parallel < 1 || parallel > 100) {
            throw new IllegalArgumentException(
                    "COUNT >= 1 and 1 <= PARALLEL <= 100");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        ExecutorService pool = Executors.newFixedThreadPool(parallel);
        List<Future<Outcome>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= count; i++) {
                final int requestId = i;
                Callable<Outcome> job =
                        () -> call(client, base, requestId);
                futures.add(pool.submit(job));
            }

            int ok = 0;
            int retried = 0;
            List<Integer> missing = new ArrayList<>();
            Map<String, Integer> byVersion = new HashMap<>();

            for (Future<Outcome> future : futures) {
                Outcome outcome = future.get();

                if (outcome.success()) {
                    ok++;
                    byVersion.merge(
                            outcome.revision(), 1, Integer::sum);
                } else {
                    missing.add(outcome.id());
                    System.err.println("FAILED id=" + outcome.id()
                            + " detail=" + outcome.detail());
                }

                if (outcome.attempts() > 1) {
                    retried++;
                }
            }

            System.out.println("planned=" + count);
            System.out.println("succeeded=" + ok);
            System.out.println("failed=" + missing.size());
            System.out.println("retriedIds=" + retried);
            System.out.println("revisions=" + byVersion);
            System.out.println("missingIds=" + missing);

            if (!missing.isEmpty()) {
                System.exit(1);
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Run

Java 17 source-file mode allows:

~~~bash
java RolloutProbe.java http://localhost:8080 200 12
~~~

From a test Pod with Java 17 inside the cluster:

~~~bash
java RolloutProbe.java \
  http://rollout-verifier.default.svc.cluster.local 200 12
~~~

**Illustrative sample output**, not fixed output:

~~~text
planned=200
succeeded=200
failed=0
retriedIds=3
revisions={v1=92, v2=108}
missingIds=[]
~~~

If you see only v1 or only v2, the test might not have overlapped while both ran or connections stayed pinned to one Pod; do not immediately assume an error. Send continuous requests spanning the rollout window across enough connections.

### What counts as a pass?

1. `planned` equals the number of unique logical IDs sent.
2. `succeeded=planned` and `missingIds=[]` within at most 5 attempts.
3. If `retriedIds>0`, those are **transient failures masked by retries**, so you cannot claim zero errors. Record the count and root cause.
4. `revisions` includes both v1 and v2 when proving the test hit the overlap window.
5. Client results match ingress access logs and server node/version logs.
6. **This only verifies GET responses**, not zero lost side effects for POSTs or background jobs.

In authenticated environments, test clients must authenticate validly without logging raw credentials. Cap `COUNT`/`PARALLEL` within staging capacity; avoid generating unauthorized load.

## 12. When DB COMMIT succeeds yet the response is lost

~~~text
Client POST /orders, key K
       |
       v
Pod v1 executes INSERT and COMMIT
       |
       v
Pod receives SIGKILL / network resets
       |
       X response 201 never reaches client
       |
       v
Client retries POST /orders with same key K
~~~

If the client does not know whether the operation succeeded, retrying is a reasonable recovery, yet risks creating **two orders** if the server lacks idempotency. Therefore **graceful shutdown alone cannot make retries safe**.

A mutation API should use:

- High-entropy client-generated `Idempotency-Key`, scoped by tenant/actor/action.
- Unique constraint in a durable DB.
- Request hash so the same key with a different payload is rejected.
- A transaction binding business effect and idempotency result when in the same database.
- Defined concurrency conflict/wait/status semantics when the same key is still in flight.
- When retried after COMMIT, returning the **same result/resource ID** without re-executing the effect.
- TTL/retention matching the retry window; expired keys lose eternal dedup guarantees.
- External payments/emails/webhooks requiring provider idempotency, outboxes/inboxes, or separate reconciliation.

### Illustrative SQL (not a complete API)

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(64) NOT NULL,
    operation_type VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    response_status INT,
    response_body TEXT,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);

CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

**Workflow**:

~~~text
authenticate + authorize principal and tenant
validate request and idempotency key
BEGIN TRANSACTION
    claim unique (tenant, operation, key)
    if existing result:
        compare request hash
        return recorded outcome or conflict
    insert business row exactly once
    record final result with same key
COMMIT
return result
~~~

Transaction isolation, unique-key conflict handling, and concurrent retries must be implemented/tested for your specific DB. Never validate this solely with an in-JVM `ConcurrentHashMap`; v1/v2 running across **two Pods** could still both execute the effect.

If the side effect is an external payment, an SQL transaction cannot roll back an external charge. You need provider idempotency keys and reconciliation by transaction ID; never claim exactly-once from a local unique record alone.

### 201, 202, and timeouts

- **201 Created** after DB commit: state is durably persisted, yet the response can still be lost. Clients look it up by key.
- **202 Accepted** should only be returned once the request/job is **durably** enqueued and the client receives an operation ID to poll progress.
- **HTTP 503/504** does not tell you whether the side effect COMMITTED or not. It can come from the gateway, network, or server after commit.
- **POST retries** must rely on idempotency contracts and backoff, never blind arbitrary retries.

## 13. Background workers, Kafka, RabbitMQ, and outbox

Rolling deployments typically keep v1 and v2 alive concurrently. Beyond HTTP handlers, apps may run Kafka listeners, RabbitMQ consumers, scheduled jobs, and async executors.

### Kafka/RabbitMQ consumer

A safe flow requires:

1. Stop consuming new messages when the Pod drains.
2. Finish in-flight messages within budget.
3. ACK/commit offsets **only after** business effects are durably persisted per processing contract.
4. If the Pod dies before ACK, the broker may redeliver; handlers must be **idempotent**.
5. Bound retries/poison messages and configure a DLQ if needed.
6. Distinguish Pod graceful exit from crashes, rebalancing, and zombie consumers.

**Kafka:** committing offsets before DB commit can lose effects; committing offsets after DB commit can cause replay after a crash. Transactional/idempotent design is needed. **RabbitMQ:** ACKing too early causes the same loss; unacked messages are usually redelivered when a consumer/connection dies.

### Outbox pattern

~~~text
HTTP request
    |
    v
DB transaction:
    update business state
    insert outbox event
COMMIT
    |
    v
outbox publisher -> broker -> idempotent consumer
~~~

If Pod v1 stops after commit yet before publish, the outbox record remains in the DB and another publisher picks it up. Messages can be re-sent if a publish acknowledgment is lost, so consumers must still deduplicate by event ID.

### Scheduled jobs

`@Scheduled` does not automatically guarantee single-instance execution across multi-replica Deployments. During v1/v2 overlap, both can run the job at once. For run-once tasks, use distributed leases/leader election, dedicated workers/schedulers, or transactional DB claims.

### Async executors

`@Async` or manually created `ExecutorService` provides no durability on its own. Returning HTTP 202 after putting a task only into an in-memory queue risks losing it on Pod restart. Manage lifecycles, bounded queues, shutdown/awaitTermination, and durable jobs when business recovery is required.

## 14. Long-lived connections: SSE, WebSocket, gRPC

| Connection type | Issue during rollout | Approach |
| --- | --- | --- |
| HTTP keep-alive | Reuses connection to old Pod | Draining and client retry/idempotency |
| HTTP/2 | Multiple streams over one connection | Transport GOAWAY/drain support, stream lifetime |
| SSE | One response open for hours | Last-Event-ID, durable event replay/resync |
| WebSocket | TCP session cannot move directly across Pods | Close/reconnect/reauth/resume |
| gRPC unary | RPC COMMITs yet response times out | Idempotency + deadline/retry contract |
| gRPC streaming | Stream severed mid-events | Checkpoint/resubscribe, sequence dedup |
| File upload | Partial request body received | Resumable upload + checksum + cleanup |
| File download | Client receives partial file | Range requests/ETag/checksum if supported |

**Important:** a v1 WebSocket/SSE connection does not automatically “migrate” to process v2 when Service endpoints update. If a stream carries critical events, provide sequence IDs and a durable/replay source. SSE `Last-Event-ID` does not create a replay log by itself; the server must implement it.

Never stretch Spring graceful timeouts to hours just for WebSockets. Use max stream lifetimes, graceful close signals, client reconnect + resume, and bounded per-client queues. Verify gaps/duplicates against the durable source rather than just counting reconnections.

Once HTTP 200 response headers are sent, they cannot change to 503 if the body is cut off mid-stream. Therefore, access-log status 200 does not prove the client received the entire stream.

## 15. Version compatibility: v1 and v2 coexisting

Even with proper shutdown, v1/v2 can break while sharing databases, sessions, brokers, or external APIs.

Checklist:

- **Schema expand/contract:** add compatible columns/tables first; wait until zero v1 pods remain before dropping old columns.
- **Session serialization:** `HttpSession` stored in an old Pod's JVM disappears when clients switch Pods; consider Spring Session shared stores or stateless designs.
- **Auth keys/tokens:** v1/v2 must verify the same issuer/signing keys/cookie policies.
- **Cache format:** do not let v2 write cache objects that v1 cannot deserialize.
- **Message schemas:** v2 producers and v1 consumers must stay mutually readable during overlap.
- **API contracts:** v1/v2 accept payloads from old and new clients per compatibility policy.
- **Flyway/Liquibase:** avoid running destructive migrations during the overlapping window.
- **Flags:** avoid enabling v2-only features while traffic still routes to v1.
- **Rollback:** if v2 wrote incompatible data, rolling back v1 code does not undo migrations automatically.

A health probe returning UP does not verify this compatibility. You need contract tests across both revisions, DB migration tests, canaries, and rollback rehearsals.

## 16. Evidence checkpoints via logs and metrics

An evidence table should include:

| Field | Why |
| --- | --- |
| Synthetic request ID | Compare planned, succeeded, missing |
| Client attempt number | Measure retries without hiding errors |
| Client send/receive timestamps | Align onto rollout timeline |
| Client HTTP status/EOF/timeout | Distinguish success vs failure |
| Target revision/node | Know whether v1 or v2 handled it |
| Ingress upstream IP/status | Separate LB errors from origin |
| Spring handler start/completion | Separate new requests from in-flight |
| Durable operation ID/COMMIT time | Proof of completed business work |
| Idempotency key/hash/result | Detect duplicates and reconciliation |
| EndpointSlice terminating transition | Exact point Pod was pulled from routing |
| SIGTERM/shutdown start/end | Measure real grace duration |
| Pod exit reason/code | Separate graceful, OOM, SIGKILL |
| SSE event sequence/replay | Detect gaps/duplicates after reconnect |

Useful metrics: `http.server.requests` by status/route/revision, in-flight requests, active connections, readiness failures, ingress 502/503/504, shutdown duration, DB commit counts, queue consumer lag, retries, missing/duplicate logical IDs, SSE reconnect/event lag.

**Never put raw access tokens, session IDs, emails, or high-cardinality request IDs in Prometheus metric labels.** Put request IDs in access-controlled/retention-bounded logs; metrics use route templates, revisions, pods, statuses, and outcomes.

### Diagnosing a 502 during rollout

~~~text
Client ID=71 -> 502
    |
    v
Ingress upstream points to old Pod?
    | YES: connect refused after Pod stopping
    |      -> LB propagation/draining race
    |
    | NO: upstream responds slowly
           |
           v
    Spring handler started?
       | NO: proxy/connector/capacity issue
       | YES: DB committed?
                | YES: reconcile result and retry safely
                | NO: retry under contract/idempotency
~~~

An edge 502 does not necessarily show up in origin logs. Nor does a server-side HTTP 200 prove the client received the full response. You must **reconcile end-to-end** from client to DB.

## 17. Designing acceptance gates

In a staging test run, you can pick:

| Gate | Criterion |
| --- | --- |
| Rollout | `kubectl rollout status` succeeds and v2 is Ready |
| Coverage | Load generator runs before, during, and after v1→v2 |
| IDs | Planned logical IDs match, none missing in test ledger |
| GET eventual success | `succeeded=planned`, `missingIds=[]` within bounded retries |
| Transient errors | Explicitly report retries, 502/503/EOF/timeouts within error budget |
| Revisions | Both v1/v2 appear in responses/logs when testing overlap |
| Drain | Requests dispatched before SIGTERM get time to finish |
| Business operations | Durable committed unique IDs match accepted IDs |
| Duplicate effects | Each idempotency key produces only one business effect |
| Async jobs | Queues/outboxes have redelivery/recovery, zero lost messages |
| Streaming | Replay/resume loses zero durable events |
| Compatibility | v1/v2 validly access shared DB/sessions/messages |
| Rollback | Routing and data contracts recover cleanly if v2 fails |

**Never mistake eventual success=100% for zero transient errors.** If `retriedIds>0`, failures occurred and must be accounted for in availability budgets. If GET tests pass while POSTs produce duplicate charges, the overall “zero lost/corrupted business operations” bar still fails.

## 18. Failure injection to map system boundaries

Run only in **authorized staging/localhost**, with bounded load and a rollback plan:

1. Normal v1→v2 rolling update, comparing IDs per attempt.
2. Remove/shorten preStop and observe upstream connect resets at ingress.
3. Set graceful timeout shorter than a 5-second request and observe failures.
4. Send SIGTERM when a request is confirmed in-flight.
5. Send SIGKILL to a Pod: **do not expect graceful shutdown**; verify idempotent recovery.
6. Make the new Pod report readiness UP too early; measure warm-up errors.
7. Briefly break DB connectivity: liveness should not restart the entire fleet.
8. Sever response after DB COMMIT; retry with the same idempotency key.
9. Two Pods process POSTs with the same key concurrently; unique constraints must prevent double effects.
10. Kill a queue consumer after DB commit before ACK; it must redeliver safely.
11. Reconnect SSE during Pod replacement; check for sequence gaps.
12. Reconnect/reauth/resume WebSockets; do not expect TCP migration.
13. Test rollback with compatible schema migrations and new feature flags.
14. Verify increased load while one Pod is draining: DB pools and memory must still suffice.

**SIGTERM is a graceful test; SIGKILL/OOM/node loss is a recovery test.** They prove different properties and must never be conflated into one conclusion.

## 19. Rollback and canary

Kubernetes Deployment RollingUpdate does not split traffic by exact percentages like a 1% canary. To verify fractional traffic, use an ingress/service mesh/Argo Rollouts or suitable routing tool.

A workflow:

1. Release v2 to a slice of traffic in staging/canary.
2. Send synthetic reads + idempotent write operations with correlation IDs.
3. Measure errors/retries/latency/DB state on both v1 and v2.
4. If gates pass, ramp up v2 traffic while watching HPA/resources/queue lag.
5. If gates fail, pause, reconcile data, and roll back per plan.

Deployment rollback commands when authorized:

~~~bash
kubectl rollout history deployment/rollout-verifier
kubectl rollout undo deployment/rollout-verifier
kubectl rollout status deployment/rollout-verifier --timeout=180s
~~~

Rollback **is also a transition** needing draining/availability tests. It does not automatically reverse schemas or side effects written by v2; never roll back after destructive DB migrations without a data compatibility plan.

## 20. Anti-patterns to eliminate

| Anti-pattern | Risk | Better practice |
| --- | --- | --- |
| Watching only `kubectl rollout status` | Misses lost HTTP/DB effects | Load generator + request IDs + durable reconciliation |
| Only enabling `server.shutdown=graceful` | Ignores LB propagation | EndpointSlice/readiness + preStop when measured as needed |
| 10s preStop with 10s termination grace | Zero time left for Spring to stop | Sum preStop + graceful + margin |
| Assuming `maxUnavailable=0` means zero 502s | LB/network races still occur | End-to-end edge/client metrics |
| Using `port-forward` on Service as an LB test | Usually pins to a single Pod | Hit actual Service DNS/Ingress |
| Testing only before or after rollout | Misses the dangerous transition window | Send traffic continuously across the rollout |
| Retrying POSTs blindly | Duplicate effects | Idempotency + DB unique constraints |
| Returning 202 before job is durably enqueued | Lost jobs on Pod restart | Transactional enqueue/outbox |
| Kafka ACK before DB commit | Lost event effects on crash | Commit/ACK after durability + dedup |
| `@Scheduled` running on every Pod | Double execution during overlap | Distributed leader/lease/job queue |
| In-memory app counters as source of truth | Counters vanish when Pod dies | Durable operation ledger |
| Ignoring 502s because retries got 200 | Masks transient errors | Report attempts, retries, error SLOs |
| Using SIGKILL to test graceful shutdown | Shutdown hooks do not run | SIGTERM for graceful, SIGKILL for recovery |
| Stopping long SSE by setting infinite timeouts | Rollouts hang, exhausts resource budgets | Reconnect, replay, TTLs |
| Liveness checking shared DB | Restart storm when DB glitches | Purpose-built readiness/circuit breakers |
| Testing only a single Pod | Misses old/new compatibility bugs | Multi-replica overlap |
| Public drain endpoint | Can be abused to make Pods unready | Protected control-plane orchestration |
| Code rollback after destructive schema migration | v1 cannot read data | Expand/contract and rollback rehearsals |

## 21. Production checklist before signing off “zero lost requests”

- [ ] Defined logical requests, HTTP attempts, durable operations, and error budgets?
- [ ] Enabled graceful shutdown per exact Spring Boot version and measured real SIGTERM?
- [ ] Container ENTRYPOINT forwards stop signals properly to the JVM?
- [ ] Termination grace covers preStop + measured shutdown + margin?
- [ ] `maxSurge`/`maxUnavailable`/replicas and cluster resources provide enough capacity?
- [ ] v2 readiness turns UP only once warmup and required dependencies are ready?
- [ ] Liveness does not restart the whole fleet on shared dependency outages?
- [ ] Terminating EndpointSlices and external LB drain have been measured?
- [ ] Client load tests track unique IDs, per-attempt errors/retries, and revisions?
- [ ] Requests started before SIGTERM are traced through to response/client receipt?
- [ ] POST side effects have durable idempotency and conflict/reconcile APIs?
- [ ] Queue consumer ACKs/offsets and background jobs have shutdown recovery?
- [ ] SSE/WebSocket/gRPC have reconnect/resume and event sequence gap checks?
- [ ] Shared DB schemas, session stores, caches, and messages are v1/v2 compatible?
- [ ] Verified graceful errors and SIGKILL/node-loss recovery separately?
- [ ] Logs/metrics exist across ingress, Pod lifecycle, Spring, and durable stores?
- [ ] Canary/rollback plan preserves data without duplicating business operations?
- [ ] Runbook exists to pause rollouts, investigate missing IDs, and reconcile operations?

## 22. Self-check questions

**1. Does `server.shutdown=graceful` prevent all HTTP 502s during rolling updates?**

**Answer:** No. LBs can hold old endpoints, clients reuse keep-alive, or nodes can die. Draining and end-to-end verification are required.

**2. Is an 8s preStop sleep added on top of `terminationGracePeriodSeconds`?**

**Answer:** No. The hook consumes from the same termination grace, before SIGTERM.

**3. How do readiness and liveness differ?**

**Answer:** Readiness decides whether to receive new requests; liveness decides whether the instance should restart. Never tie liveness blindly to shared DB outages.

**4. Does `maxUnavailable=0` prove zero lost requests?**

**Answer:** Not yet. It only controls Pod availability during rollout, not whether clients received responses or DB commits succeeded.

**5. Why send GETs continuously across applying v2?**

**Answer:** Only traffic spanning the draining/overlap window exposes failures caused by endpoint transitions.

**6. A test achieves 200/200 IDs succeeded after retries, with 3 IDs retried—is that zero transient errors?**

**Answer:** No. Eventual success passed, yet transient failures occurred and must be investigated.

**7. When a POST COMMITTED yet the response was lost, what should the client do?**

**Answer:** Reconcile/query by idempotency key or retry **with the same key** per contract, avoiding duplicate effects.

**8. Does an API returning 202 after enqueuing a job only in memory guarantee zero lost jobs on Pod stop?**

**Answer:** No. Accepted requires a durable queue/outbox before acknowledging.

**9. Does SIGKILL run the Spring graceful shutdown hook?**

**Answer:** No. SIGKILL tests crash recovery/idempotency, not graceful shutdown.

**10. Does SSE having `Last-Event-ID` make resuming safe automatically?**

**Answer:** No. The server must have a durable event log and ID-based replay/resync logic.

**11. Can v1 and v2 sharing a DB cause errors even when graceful shutdown works?**

**Answer:** Yes. Schema/session/message compatibility is mandatory during the coexistence window.

**12. Does `kubectl port-forward` on a Service prove HTTP requests distribute evenly across Pods?**

**Answer:** No. It usually forwards to a single Pod; test through the actual Service/Ingress.

## 23. Official sources for cross-reference

- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): grace config, how servers accept/reject new requests.
- [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): readiness, liveness, lifecycles, and probes.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, maxSurge, maxUnavailable, minReadySeconds.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): SIGTERM, SIGKILL, termination grace, and terminating EndpointSlices.
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop hook runs before TERM and counts in grace period.
- [Kubernetes — Endpoint Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): ready, serving, terminating states, and draining.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): DB transaction boundaries and durability.
- [Spring Framework — SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle of managed beans.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): safe/idempotent HTTP operations, status semantics, and retries.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/): shared sessions across multiple Pods.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): consumer lifecycles, offsets/ACKs, and transactional patterns.

**Conclusion:** Verifying zero lost requests during a Spring Boot version rollout means **measuring traffic across the rollout, separating already-started requests from new requests, verifying draining and client receipts, and reconciling durable business state**. Graceful shutdown, readiness, Kubernetes `rollingUpdate`, and `preStop` form the orchestration layer; idempotency, outbox/queue recovery, version compatibility, and controlled retries preserve business correctness when a connection or Pod is truly lost.
