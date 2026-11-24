# Mapped Ports, Container Networks, and Application-to-Service URLs in Testcontainers

## 1. One service, multiple addresses — choose the URL based on where the application runs

When writing Spring Boot integration tests with Testcontainers, you may see a container reach `STARTED` yet the application still fails with `Connection refused`, `UnknownHostException`, or a timeout. The common culprit is not a broken service, but **a URL built for the wrong client location**.

For example, an HTTP service listens inside its container on **port 5678**. Docker may publish that port to a **random host port** such as 49172. If two containers are attached to the same user-defined Docker network, the service can also be reached via a **DNS alias** such as `echo-service:5678`.

```text
                           TEST MACHINE / JVM
                         Spring Boot integration test
                                     |
                                     | http://<getHost()>:<getMappedPort(5678)>
                                     v
                    +-----------------------------------+
                    | Docker host / published TCP port  |
                    | e.g.: host:49172 -> 5678          |
                    +-----------------+-----------------+
                                      |
                                      v
        +----------- Docker user-defined network --------------+
        |                                                       |
        |  [service container]                  [app container]  |
        |  alias: echo-service                  HTTP client      |
        |  listen: 0.0.0.0:5678                     |            |
        |          ^                                  |            |
        |          +------ http://echo-service:5678 --+            |
        |                                                       |
        +-------------------------------------------------------+
```

The numbers and hostnames in the diagram are **illustrative only**: the host port is allocated by Testcontainers at container startup, with no fixed value to put into config files.

**The two most important rules:**

1. **JVM/test process → service container:** `container.getHost()` paired with `container.getMappedPort(INTERNAL_PORT)`, after the container has started.
2. **Application container → service container on the same Docker network:** `http://<network-alias>:<INTERNAL_PORT>`, **do not use the mapped host port** for the internal path.

No single URL is "correct everywhere." Always ask: **is the process actually opening the socket running on the host, inside which container, or on another network?**

## 2. Terms you must distinguish

| Term | Meaning | Example |
|---|---|---|
| **Container port** | Port the service process listens on **inside the container** | HTTP echo: `5678` |
| **Exposed port** | Internal port declared so Testcontainers/Docker publishes it to the host | `withExposedPorts(5678)` |
| **Mapped host port** | Actual TCP port on the host side assigned to an exposed port | E.g. `49172`, obtained via `getMappedPort(5678)` |
| **Container host** | Hostname/IP where **the test process** can reach published ports | `getHost()`, not always `localhost` |
| **Docker network** | Network connecting containers for direct communication | `Network.newNetwork()` |
| **Network alias** | DNS name of a container inside a user-defined network | `echo-service` |
| **Published port** | Port NATed/forwarded from the host into the container | `host:49172 → container:5678` |
| **URL from the client** | URL built for the **client's** execution environment | `http://echo-service:5678` from an app container |
| **Binding address** | Interface the server listens on inside the container | `0.0.0.0:5678` to accept connections from other containers |
| **Readiness** | Service is capable of handling requests, distinct from container merely running | `Wait.forHttp("/").forPort(5678)` |

`EXPOSE` in a Dockerfile, `withExposedPorts`, Docker CLI `-p`, and the app's actual URL are related yet **not synonymous**. A process may listen on the right internal port without being published to the host. Conversely, publishing a port cannot rescue a server bound only to `127.0.0.1` inside the container when clients arrive from another network address.

### 2.1. Distinguishing internal port from host port

Suppose Testcontainers runs:

```java
static final int HTTP_PORT = 5678;

GenericContainer<?> echo =
        new GenericContainer<>(
                DockerImageName.parse("hashicorp/http-echo:1.0.0"))
                .withExposedPorts(HTTP_PORT);
```

This is an illustrative snippet needing imports for `GenericContainer` and `DockerImageName`, and `start()` must be called before `getMappedPort`. `withExposedPorts(5678)` requests mapping internal port 5678 to **a random host port**. It does **not** mean the host also uses 5678.

After starting:

```java
echo.start();

String host = echo.getHost();
int hostPort = echo.getMappedPort(HTTP_PORT);
String url = "http://" + host + ":" + hostPort;
```

In a host-based test, that URL is the endpoint for the JVM. An `HTTP_PORT` constant bound to the service should never be overwritten with `hostPort`: the two ports have **different roles** and usually do not match.

### 2.2. Why shouldn't `getHost()` be replaced with `localhost`?

On a machine with a local Docker daemon, published ports are usually reachable at `localhost`. However, in CI, Docker-in-Docker, a remote Docker daemon, or Testcontainers Cloud, the host the JVM needs to reach **can be different**. Testcontainers' `getHost()` API returns the reachable address detected by Testcontainers for the environment.

Do not write:

```java
String wrongUrl = "http://localhost:5678";
```

and treat it as a universal URL everywhere. Port 5678 in that string is the **internal port**, and `localhost` inside another container refers to **that container itself**.

**Note:** `getHost()` does not promise to return the container's own IP. The older method name `getContainerIpAddress()` was misleading; Testcontainers recommends `getHost()` paired with `getMappedPort()`.

## 3. Rules for choosing the address by client location

| Where is the client? | Where is the service? | Host to use | Port to use | Formula |
|---|---|---|---|---|
| JVM/test runner outside service container | Testcontainers service | `service.getHost()` | `service.getMappedPort(INTERNAL)` | `http://host:mappedPort` |
| Spring Boot app running inside test JVM (`RANDOM_PORT`/`NONE`) | Testcontainers service | `service.getHost()` | `getMappedPort(INTERNAL)` | Inject `downstream.base-url` dynamically |
| App container A | Service container B, **same Docker network** | B's network alias | B's internal port | `http://service-alias:5678` |
| App container A | Service container B on a different network | No shared DNS alias | Undefined | Attach to the same network or design gateway/exposed route |
| Container A | HTTP server running on test host machine | `host.testcontainers.internal` | Host port passed to `exposeHostPorts` | `http://host.testcontainers.internal:port` |
| Test process | `PostgreSQLContainer` | `postgres.getHost()` or `getJdbcUrl()` | Mapped port for 5432 | Prefer `postgres.getJdbcUrl()` |
| App container on same network | PostgreSQL container | Alias like `postgres-db` | Internal `5432` | `jdbc:postgresql://postgres-db:5432/dbname` |
| App in Docker Compose | Compose service on same project network | Compose service name | Internal port | `http://backend:5678` |
| App in Kubernetes | Internal Kubernetes Service | Kubernetes Service DNS | Service port | Service URL, **not** Testcontainers mapping |

**Attention:** an app running in a container does not automatically share a Docker network with a service just because Docker started both. They must be **attached to the same network** or given a valid route. DNS aliases resolve only within the network the containers joined.

### 3.1. "Test host → container" vs "container → container" differ at the NAT layer

On the host → container path, Docker must publish a port and NAT/forward traffic into the internal port:

```text
test JVM -> host:mappedPort -> Docker port forwarding -> container:internalPort
```

Between two containers on the same user-defined network, the client connects directly to the target container's DNS name/service:

```text
app container -> DNS echo-service -> service container:internalPort
```

Because traffic does not traverse a host-published port, the **mapped host port plays no role** in this internal URL. Adding `withExposedPorts()` can still help if the JVM also probes or health-checks the container, but is not required just for two networked containers to talk over the internal port.

## 4. Reliable test flow from the JVM to an HTTP container

Example contract: a Spring Boot app exposes `GET /api/echo`. The controller calls `EchoGateway` via `RestClient`, and the gateway calls an HTTP service **started by Testcontainers**. We want to prove:
- Spring Boot **genuinely** calls the service container.
- The service URL uses the real **host + mapped port** obtained at runtime.
- The Spring Boot app itself listens on **a different HTTP port** allocated by `RANDOM_PORT`.
- Port 5678 is never hardcoded on the host, and no mock client makes the test falsely green.

We pick image `hashicorp/http-echo:1.0.0`, which listens on `5678` and returns text supplied via `-text`. The container is tiny and fits a network contract test. Avoid the `latest` tag so behavior does not silently drift over time.

### 4.1. Project structure

```text
build.gradle
src/main/java/com/example/portlab/
    PortLabApplication.java
    EchoGateway.java
    EchoController.java
src/test/java/com/example/portlab/
    EchoHttpIntegrationTest.java
    ContainerNetworkTest.java
```

The example uses **Java 17+, Spring Boot 3.5.8, Testcontainers, JUnit Jupiter, and a Docker/container runtime**. If your project uses Spring Boot 4.x, adjust dependencies/test APIs per your project's BOM.

### 4.2. Gradle Groovy DSL

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management picks compatible versions for starters, Spring Framework, JUnit, and Testcontainers. `org.testcontainers:junit-jupiter` integrates `@Testcontainers`/`@Container`, while `testcontainers` provides core classes like `GenericContainer` and `Network`.

This `build.gradle` is relatively minimal; running `./gradlew` requires an existing Gradle wrapper. Testcontainers needs a supported Docker-compatible runtime with image pull access. You do not need port 5678 free on the host, because Testcontainers publishes a random host port.

### 4.3. Spring Boot application class

File `src/main/java/com/example/portlab/PortLabApplication.java`:

```java
package com.example.portlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortLabApplication.class, args);
    }
}
```

This root class lets Spring component scanning discover the gateway and controller. You do not run `main()` manually when the goal is an integration test: JUnit boots the Spring context via `@SpringBootTest`.

### 4.4. Gateway using a property instead of a hardcoded URL

File `src/main/java/com/example/portlab/EchoGateway.java`:

```java
package com.example.portlab;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class EchoGateway {

    private final RestClient client;

    public EchoGateway(
            RestClient.Builder builder,
            @Value("${demo.echo.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public String fetchMessage() {
        String text = client.get()
                .uri("/")
                .retrieve()
                .body(String.class);

        return Objects.requireNonNull(text).strip();
    }
}
```

Why use `@Value("${demo.echo.base-url}")`?
- `EchoGateway` **does not know** which host port the container will publish.
- When Spring builds the bean, `demo.echo.base-url` is supplied from **`@DynamicPropertySource`** in the test.
- In production, you can inject the same property from environment variables, a config server, or deployment manifests, pointing to the real URL for your deployment topology.
- `RestClient.Builder` is auto-configured by Spring Boot's web starter; `RestClient` is a synchronous HTTP client. It fits this MVC/JUnit example; pure WebFlux typically uses `WebClient` with the same URL selection rules.

`Objects.requireNonNull(text)` makes an empty response fail clearly instead of letting a test pass with `null`. `strip()` trims any trailing newline the HTTP echo image adds; the test asserts the **business value** rather than depending on a container image's trailing newline.

### 4.5. Controller wiring the app endpoint to the gateway

File `src/main/java/com/example/portlab/EchoController.java`:

```java
package com.example.portlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    private final EchoGateway gateway;

    public EchoController(EchoGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/api/echo")
    public String echo() {
        return gateway.fetchMessage();
    }
}
```

When the HTTP test calls `/api/echo`, the execution path is:

```text
TestRestTemplate [JVM]
    -> Spring Boot HTTP listener [RANDOM_PORT]
    -> EchoController
    -> EchoGateway / RestClient
    -> http://<echo.getHost()>:<echo.getMappedPort(5678)>/
    -> Testcontainers HTTP echo service
    -> response "hello-from-container"
```

**Two dynamic ports:** `@LocalServerPort` is the port listened on by **the Spring Boot application**; `echo.getMappedPort(5678)` is the port published by **Docker for the service container**. They are two independent entities and are not interchangeable.

### 4.6. Complete JUnit integration test: app → container

File `src/test/java/com/example/portlab/EchoHttpIntegrationTest.java`:

```java
package com.example.portlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EchoHttpIntegrationTest {

    private static final int ECHO_PORT = 5678;

    @Container
    static final GenericContainer<?> ECHO =
            new GenericContainer<>(
                    DockerImageName.parse("hashicorp/http-echo:1.0.0"))
                    .withExposedPorts(ECHO_PORT)
                    .withCommand(
                            "-listen=:5678",
                            "-text=hello-from-container")
                    .waitingFor(
                            Wait.forHttp("/")
                                    .forPort(ECHO_PORT)
                                    .forStatusCode(200));

    @DynamicPropertySource
    static void echoProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.echo.base-url", () ->
                "http://" + ECHO.getHost()
                        + ":" + ECHO.getMappedPort(ECHO_PORT));
    }

    @Autowired
    TestRestTemplate http;

    @LocalServerPort
    int applicationPort;

    @Test
    void springBootReallyCallsEchoContainer() {
        ResponseEntity<String> response =
                http.getForEntity("/api/echo", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "hello-from-container",
                response.getBody());
    }

    @Test
    void applicationPortAndContainerMappingAreKnownAtRuntime() {
        assertTrue(ECHO.isRunning());
        assertNotNull(ECHO.getHost());
        assertTrue(ECHO.getMappedPort(ECHO_PORT) > 0);
        assertTrue(applicationPort > 0);

        // Do not assert that the two ports differ:
        // host ports are dynamically assigned, so collisions are possible in principle.
    }
}
```

**Meaning of annotations and APIs:**

- `@Container` marks a **static container** managed by the JUnit Testcontainers extension across the class lifecycle. The container starts before tests needing it run and stops at the end of that lifecycle.
- `withExposedPorts(ECHO_PORT)` asks Docker to publish **internal port** 5678 to an arbitrary host port.
- `withCommand("-listen=:5678", "-text=...")` makes the HTTP echo service listen on all interfaces rather than only container-internal loopback.
- `Wait.forHttp("/")` waits for **HTTP 200 on the endpoint** instead of merely waiting for the process/container to run. A started container does not prove the HTTP server is ready.
- `@DynamicPropertySource` registers a `Supplier<String>` for `demo.echo.base-url`. The supplier runs when the property is resolved; by that time the container must have started so `getMappedPort` returns a value.
- `TestRestTemplate` sends HTTP into **the Spring Boot application** on its random port. The app then calls the HTTP echo container via the injected URL.
- `getHost()` and `getMappedPort(5678)` are read **at runtime**, avoiding any fixed port number in config files.

The two `@Test` methods have distinct goals: test 1 exercises end-to-end **test client → app HTTP → downstream container**, whereas test 2 verifies startup and mapping conditions. **Test 2 alone is not proof that the endpoint is reachable**; only test 1 sends a real request.

### 4.7. How to run and expected results

Linux/macOS with Gradle wrapper:

```bash
./gradlew test --tests "com.example.portlab.EchoHttpIntegrationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.portlab.EchoHttpIntegrationTest"
```

If a project uses a Maven wrapper with equivalent dependencies:

```bash
./mvnw -Dtest=EchoHttpIntegrationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=EchoHttpIntegrationTest test
```

When Docker and dependencies are ready, **both** test methods are expected to execute. Test 1 expects HTTP 200 and body `hello-from-container`, and test 2 expects valid host/ports. **There is no fixed stdout from these tests** because the code does not call `System.out.println`; inspect the actual reports in `build/reports/tests/test/index.html` or `target/surefire-reports/` before claiming a runtime PASS.

## 5. `@DynamicPropertySource`: wiring container URLs into Spring Boot configuration

Spring TestContext provides `@DynamicPropertySource` and `DynamicPropertyRegistry` to feed endpoints allocated **during test startup** into `Environment`.

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("demo.echo.base-url", () ->
            "http://" + ECHO.getHost()
                    + ":" + ECHO.getMappedPort(5678));
}
```

A `@DynamicPropertySource` method normally must be **static**, return `void`, and accept a single `DynamicPropertyRegistry` argument. The supplier is evaluated **when the property is accessed**, not necessarily when the registration method runs.

### 5.1. Why not construct the URL before the container starts?

This is an anti-pattern:

```java
static final String WRONG_URL =
        "http://" + ECHO.getHost() + ":"
                + ECHO.getMappedPort(5678);
```

If `ECHO` has not started yet during static initialization, `getMappedPort` has no mapping and throws `IllegalStateException`. Use a `Supplier` via `@DynamicPropertySource` or code running **after `container.start()`**.

Subtle detail: a lazy `Supplier` **is not magic**. If a bean demands the property before the container has actually started, the test still fails. Coordinate lifecycle properly — e.g., a static `@Container` managed by the JUnit extension while the Spring test context initializes in order.

### 5.2. Which properties belong to the client, and which to the server?

| Property | Belongs to | Meaning |
|---|---|---|
| `server.port=0` / `@SpringBootTest(RANDOM_PORT)` | **Spring Boot application** | App HTTP server binds a random port |
| `demo.echo.base-url` | **HTTP client inside the app** | Base URL of the downstream service |
| `spring.datasource.url` | **JDBC client inside the app** | JDBC URL to the test database |
| `spring.data.redis.host/port` | **Redis client inside the app** | Test Redis endpoint |
| `spring.kafka.bootstrap-servers` | **Kafka client inside the app** | Advertised bootstrap servers matching topology |
| `getMappedPort(5678)` | **Testcontainers service** | Host port published for internal port 5678 |

Do not feed `echo.getMappedPort(5678)` into the application's `server.port`. That does not configure the downstream URL — it makes the app try to bind a port Docker may already be using. The two sides have completely separate roles.

### 5.3. Precedence of dynamic properties

In Spring TestContext, properties registered by `@DynamicPropertySource` have **higher precedence** than `@TestPropertySource`, system properties, environment variables, or regular `@PropertySource` entries. Thus, when a test unexpectedly connects to a container even though `application-test.yml` lists another host, check dynamic properties.

If a base class uses `@DynamicPropertySource` across subclasses where each subclass swaps containers/endpoints, Spring's context cache can retain a bean with the old URL. In that situation, align container lifecycle scope or use `@DirtiesContext` deliberately — **do not put `@DirtiesContext` on every test by default**.

## 6. Docker networks and DNS aliases: app container → service container

When **both client and service run inside containers**, the natural way to connect them is sharing a user-defined Docker network and using a **network alias**.

```java
try (Network network = Network.newNetwork()) {
    // Attach service and app container to the same network.
    // The service is called via "echo-service:5678".
}
```

`Network` is a Testcontainers resource; import `org.testcontainers.containers.Network` and close it after the test. **Do not assume from `withExposedPorts` that two containers share a network**; they are completely separate concepts.

### 6.1. URL based on where the application runs

With the service container aliased as `echo-service`, a process inside the **client/app container** calls:

```text
http://echo-service:5678/
```

Do not call:

```text
http://localhost:5678/       # localhost refers to the app container ITSELF
http://echo-service:49172/   # 49172 is the host mapped port, not the internal port
```

These are illustrative values; when the service uses TLS/HTTPS, the URL must use `https`, valid certificates/trust configuration, and the container must listen on the matching port. Do not switch to HTTPS blindly just because a Docker network alias exists.

**DNS aliases are network-scoped**. The name `echo-service` will generally not resolve inside a JVM running on the host, because that JVM is not in the user-defined network's Docker DNS domain. If the test JVM calls the service directly, use `getHost()+getMappedPort()` even if the container also has a network alias.

### 6.2. Complete JUnit Testcontainers example: container A calls container B

The test below starts an HTTP echo server and an Alpine container on **the same network**. Alpine runs BusyBox `wget` to send an HTTP request to the server's alias. **No mapped host port is needed** for the two containers to talk.

File `src/test/java/com/example/portlab/ContainerNetworkTest.java`:

```java
package com.example.portlab;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContainerNetworkTest {

    private static final int INTERNAL_HTTP_PORT = 5678;

    @Test
    void clientContainerUsesDnsAliasAndInternalPort() throws Exception {
        try (
                Network network = Network.newNetwork();

                GenericContainer<?> service =
                        new GenericContainer<>(
                                DockerImageName.parse(
                                        "hashicorp/http-echo:1.0.0"))
                                .withNetwork(network)
                                .withNetworkAliases("echo-service")
                                .withExposedPorts(INTERNAL_HTTP_PORT)
                                .withCommand(
                                        "-listen=:5678",
                                        "-text=from-network")
                                .waitingFor(
                                        Wait.forHttp("/")
                                                .forPort(INTERNAL_HTTP_PORT)
                                                .forStatusCode(200));

                GenericContainer<?> client =
                        new GenericContainer<>(
                                DockerImageName.parse("alpine:3.20"))
                                .withNetwork(network)
                                .withCommand("sh", "-c", "sleep 120")
        ) {
            service.start();
            client.start();

            // Execute wget INSIDE the client container.
            Container.ExecResult response =
                    client.execInContainer(
                            "wget",
                            "-q", "-O", "-",
                            "http://echo-service:5678/");

            assertEquals(0, response.getExitCode());
            assertEquals(
                    "from-network",
                    response.getStdout().trim());

            assertTrue(service.isRunning());
            assertTrue(client.isRunning());
        }
    }
}
```

This is a **JUnit test running against a real container runtime** with appropriate images. Key points:

- `Network.newNetwork()` creates an isolated user-defined network for the test.
- `service.withNetwork(network)` and `client.withNetwork(network)` attach both containers to **the same network**.
- `service.withNetworkAliases("echo-service")` creates a DNS name resolvable by the client container.
- `withExposedPorts(5678)` on `service` here supports **readiness checks from the host**; the command inside Alpine does **not** use the mapped port.
- `Wait.forHttp("/")` ensures the server returns HTTP 200 before starting the client.
- `execInContainer` runs `wget` from inside the client container. Therefore `echo-service:5678` is the **true endpoint** from that client's perspective.
- `try-with-resources` closes client, service, and network afterward, reducing resource leaks.
- `alpine:3.20` includes BusyBox `wget` by default. With a custom client image lacking that tool, use whatever client tool is installed instead of concluding networking is broken.

**Distinguishing results:** A passing container-network test proves the DNS alias and container-to-container route work inside the created network. It **does not prove** that the Spring Boot app in the test JVM uses that alias; the host-based app belongs to the separate test in Section 4.

### 6.3. What if the Spring Boot application itself is packaged as a container?

When the app runs in container A and the backend runs in container B, pass configuration matching **the address visible to container A**, for example:

```properties
demo.echo.base-url=http://echo-service:5678
```

This is an **illustrative configuration**, valid only when both containers share the network and service B has alias `echo-service`. To supply it via environment variable to Spring Boot:

```text
DEMO_ECHO_BASE_URL=http://echo-service:5678
```

Spring Boot relaxed binding maps this environment variable name to `demo.echo.base-url`. The test code launching the app container must provide variables/connection details for the **container network**, not the `getHost()+getMappedPort()` URL meant for the test JVM.

Conversely, if **the Spring Boot test runs directly inside the JVM** (not inside an app container), it needs the published host address from `getHost()`/`getMappedPort()`, even if the Docker daemon sits on a remote host. Saying "Spring Boot application" does not decide the URL; **where the application process runs** decides it.

## 7. Container → host process: `host.testcontainers.internal`

Another direction: an HTTP server or mock service runs **on the test host machine**, while the client runs inside a container. Here the client container cannot use `localhost`, because `localhost` points to the container itself.

Testcontainers lets you expose a **host port** to containers started afterward:

```java
// Step 1: host HTTP server has STARTED and is listening on localPort.
Testcontainers.exposeHostPorts(localPort);

// Step 2: only then start the client container.
// Inside the container, call:
// http://host.testcontainers.internal:<localPort>/
```

This is an **illustrative snippet**, requiring `org.testcontainers.Testcontainers` and a `localPort` obtained from a real server. It will not run standalone without a host server.

Required sequence:
1. **Start the server on the host** and find the actual port it is listening on.
2. Call `Testcontainers.exposeHostPorts(localPort)` **before starting** the client container.
3. Start the client container.
4. From inside the client container, call `http://host.testcontainers.internal:localPort/`.
5. Shut down client/server and release the port after the test.

Testcontainers handles forwarding so `host.testcontainers.internal` works across different Docker environments. Never replace it with `127.0.0.1` inside the container. Depending on configuration, `container.withAccessToHost(true)` may be relevant, yet it **does not replace** registering the port via `exposeHostPorts` when that model is required.

### 7.1. Testing a host HTTP server with `RANDOM_PORT`

Suppose Spring Boot runs a real HTTP server with `@SpringBootTest(RANDOM_PORT)` and `@LocalServerPort int appPort`. If you want a containerized client to call back into **the Spring Boot app on the host**, expose `appPort` with `Testcontainers.exposeHostPorts(appPort)`, then start the client container, and have it call:

```text
http://host.testcontainers.internal:<appPort>/api/echo
```

**Avoid reversing the order:** if the client container starts before `appPort` is known and `exposeHostPorts` is called, forwarding may not be active. If a test extension starts the container too early, move the client container's lifecycle so it starts after the application server is up.

### 7.2. Host-to-container and container-to-host URLs are not interchangeable

- **Host → container**: `container.getHost()` + `container.getMappedPort(internal)`.
- **Container → host**: `host.testcontainers.internal` + exposed `localPort`.
- **Container → container**: `network alias` + `internal port`.

These are three distinct topologies. Never share one hardcoded `service.url` across all three when the application runs in different locations.

## 8. PostgreSQL, Redis, Kafka: which URL connects the app to the service?

One of the biggest pitfalls when moving from an HTTP container to stateful services is that **each client formats its endpoint differently**. Network rules remain the same, while URL/connection syntax differs.

### 8.1. `PostgreSQLContainer` from a Spring Boot test JVM

`PostgreSQLContainer` builds a JDBC URL containing the mapped host/port and database name. When Spring Boot **runs inside the test JVM**, use:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("app_test")
                .withUsername("test")
                .withPassword("test");

@DynamicPropertySource
static void dbProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

This is an **illustrative snippet in a `@Testcontainers` Spring Boot test**, needing imports for `PostgreSQLContainer`, `Container`, `@DynamicPropertySource`, `DynamicPropertyRegistry`, the `org.testcontainers:postgresql` dependency, and the PostgreSQL driver. Never assemble `jdbc:postgresql://localhost:5432` by hand: the container's `getJdbcUrl()` reflects the real mapped host port.

**When the app runs in its own container on the same Docker network**, its URL uses the alias and internal port:

```text
jdbc:postgresql://postgres-db:5432/app_test
```

The prerequisite is that the PostgreSQL container joins the same Docker network under alias `postgres-db`, with matching credentials/schema. `postgres.getJdbcUrl()` fits the host test JVM, **not necessarily inside another app container**, because it contains a host address/host-published port that may be unnecessary or unreachable from inside an app container.

### 8.2. Redis: host, port, TLS, password

From the test JVM:

```java
registry.add("spring.data.redis.host", redis::getHost);
registry.add("spring.data.redis.port",
        () -> redis.getMappedPort(6379));
```

This example belongs inside `@DynamicPropertySource`, with an already-started `redis` container. If the Redis client lives inside a container on the same Docker network with alias `redis-cache`, use host `redis-cache` and internal port `6379`.

Do not equate TCP reachability with Redis readiness or authentication. Configure passwords, ACLs, and TLS/scheme appropriately and verify real commands like `PING` or `SET/GET` in tests.

### 8.3. Kafka has advertised listeners

Kafka is not like HTTP or Redis where one host/port suffices. Clients connect initially to **bootstrap servers**, then the broker returns metadata containing **advertised listener addresses**; those broker endpoints must also be reachable from **the client's location**.

Consequently, in a test JVM using a Testcontainers Kafka container, read `kafka.getBootstrapServers()` or use supported Spring Boot `@ServiceConnection` rather than **constructing** `localhost:9092`. If an app container on a Docker network is the Kafka client, the broker needs a listener advertised for that network, not merely a container alias used as the bootstrap URL.

A test that completes TCP connection to bootstrap addresses yet fails immediately on subscribing or publishing topics often suffers an **advertised listener mismatch**, not an authentication or topic bug.

### 8.4. HTTP/HTTPS/gRPC health checks

HTTP `http://host:port`, HTTPS `https://host:port`, gRPC authorities, and JDBC URLs have distinct syntax and semantics. `getHost()+getMappedPort()` solves **network addressing**, not:
- TLS truststores, hostname verification, or mTLS identities.
- HTTP base paths or server context paths.
- gRPC HTTP/2 transport/ALPN.
- Proxy/`NO_PROXY` rules.
- Redis/Kafka/PostgreSQL protocol negotiation.
- Authentication and application readiness.

**Never make a TLS test pass by disabling certificate verification in production code.** When a service uses HTTPS, verify certificates and hostnames properly for the topology.

## 9. Spring Boot `@ServiceConnection` vs manual `@DynamicPropertySource`

Spring Boot supports **Testcontainers service connections** via `spring-boot-testcontainers` and `@ServiceConnection`. When a matching connection details factory exists, Boot creates `ConnectionDetails` automatically for services like PostgreSQL, Redis, Kafka, and RabbitMQ.

PostgreSQL example:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

This is a **fragment** added to a build with the Spring Boot BOM, not a complete `build.gradle`.

```java
@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

This illustrative class needs imports for `@Testcontainers`, `@SpringBootTest`, `@Container`, `@ServiceConnection`, and suitable JDBC/JPA app config. Once recognized by Boot, connection details mean **you do not write** `spring.datasource.url` or username/password manually.

**Do not slap `@ServiceConnection` onto an arbitrary HTTP echo `GenericContainer`:** Boot needs a `ContainerConnectionDetailsFactory` supporting that service/connection details type. For the custom `demo.echo.base-url` property in our example, **`@DynamicPropertySource` is the clean, explicit choice**.

### 9.1. Watch out when mixing ServiceConnection and properties

Spring Boot notes that **connection details can take precedence over connection-related configuration properties**. If you declare `@ServiceConnection` on PostgreSQL while also setting `spring.datasource.url` elsewhere, verify which source Boot actually uses instead of trusting one line in `application-test.yml`.

When tests use multiple datasources/Redis connections or custom containers, stick to one consistent strategy:
- Boot-recognized services: prefer service connection where appropriate.
- Custom endpoints: dynamic properties via `getHost()/getMappedPort()`.
- App container → container on same network: alias/internal port in the app container's env/config.

**Never extract an endpoint by parsing logs and feeding it into config.** Testcontainers already provides official APIs to obtain topology-appropriate connection details.

## 10. Readiness is not running: Testcontainers wait strategies

A container in `running` state does not guarantee the service inside has:
- Finished binding the TCP port.
- Completed migrations or data seeding.
- Become ready to return HTTP 200.
- Registered broker listeners.
- Begun accepting authentication/requests.

HTTP example:

```java
new GenericContainer<>(
        DockerImageName.parse("hashicorp/http-echo:1.0.0"))
        .withExposedPorts(5678)
        .waitingFor(
                Wait.forHttp("/")
                        .forPort(5678)
                        .forStatusCode(200));
```

This is an illustrative unstarted container config. `Wait.forHttp` probes the endpoint from where Testcontainers can reach the published port and waits for the expected HTTP status, rather than trusting a log line like "server started."

| Signal | Enough to claim service ready? | Reason |
|---|---|---|
| `container.isRunning()` | **Not yet** | Container process is alive; app may not be listening yet |
| `getMappedPort(internal) > 0` | **Not yet** | Docker assigned a port; protocol readiness is unverified |
| TCP socket connects | **Not necessarily** | HTTP/DB migrations/auth/broker metadata can still fail |
| HTTP health returns 200 per contract | Often **suitable for HTTP services** | Still may not verify deeper business invariants |
| Simple DB query succeeds | Proves connectivity and schema/query readiness | Does not prove transaction isolation or production load |
| App test calls downstream and asserts payload | Concrete end-to-end proof | Does not replace all security/load/migration tests |

**Pick readiness checks by protocol.** For `PostgreSQLContainer`, Testcontainers provides built-in startup/wait behavior; for Redis or Kafka, verify key commands/protocols. Never use `Thread.sleep(5000)` to guess service startup duration; tests will flake on CI.

### 10.1. Timeouts and logs

When a service fails to become ready, inspect the failing container's logs:

```java
String logs = container.getLogs();
```

That is an **illustrative snippet** assuming `container` is a Testcontainers instance. Never dump unbounded logs into CI if they contain passwords or tokens; redact and keep only diagnostic context. Consider `withStartupTimeout(Duration.ofSeconds(...))` on the container or startup check strategy when genuinely needed, rather than raising timeouts indefinitely.

Timeouts can stem from image pulls, networking, or the Docker daemon rather than app HTTP code. Separate **container create/start**, **port binding**, **readiness**, **application call**, and **assertion** into stages to isolate faults.

## 11. Remote Docker, CI, Windows, macOS, and Docker-in-Docker

Testcontainers works across Docker Desktop on Windows/macOS, Linux Docker daemons, CI executors, and Testcontainers Cloud. The crucial difference lies in **which address the test runner actually uses to reach published ports**.

- With Docker Desktop, `getHost()` typically returns a hostname reachable from the test JVM; do not assume every environment works the same way.
- With a remote Docker daemon, published ports live on **a Docker host separate from the JVM machine**. `localhost` on the JVM is therefore wrong.
- With Docker-in-Docker, multiple network namespaces exist: runner container, daemon container, and service containers may differ. `getHost()`/Testcontainers runtime config handles several topologies, yet all components must sit on a reachable network.
- With Testcontainers Cloud or remote runtimes, mapped ports are forwarded per environment mechanics; use Testcontainers' APIs rather than guessing a Docker bridge IP.
- In CI running the test JVM **inside a container**, `getHost()` is the supported entry point for Testcontainers routing; do not replace it with a container IP from `docker inspect` assuming bridge routing always works.
- Firewalls, corporate proxies, VPNs, and `NO_PROXY` rules can let a hostname resolve while HTTP clients still time out.

**Diagnostic habit:** log host, internal port, mapped port, and client runtime context on failure, while **never logging usernames/passwords/tokens or full JDBC URLs if they carry secrets**. Swapping URLs to `localhost` because "it works on my laptop" breaks portability.

## 12. Port mapping and network isolation under parallel execution

Testcontainers allocates random host ports so multiple parallel tests/containers do not trample standard ports like `5432`, `6379`, or `8080`.

Common scenarios:
- Two PostgreSQL containers both listen on `5432` **internally**; each gets a distinct host mapped port.
- Two containers on the same Docker network can both use internal `5432` under **two distinct aliases** without colliding.
- Two services sharing the same network alias `db` cause DNS ambiguity; assign **distinct, stable** aliases when tests target specific instances.
- When a container restarts, its host mapped port **can change**; never cache the URL from an old instance.
- Spring's context cache can hold a client initialized with an old endpoint if container lifetime is shorter than the context.
- `withFixedExposedPort`/fixed host port bindings invite conflicts; avoid them unless a clear requirement and coordination exist.
- Network aliases resolve only inside networks the container joined; never treat a network alias as a "global DNS name" for all test runners.

Safe parallel execution also requires avoiding duplicate keys, databases, or topics, not just port conflicts. Mapped ports eliminate **port collisions**, not shared data state collisions.

## 13. Spring context cache and container lifecycle

A subtle bug arises when each test class declares its own static `@Container`, the JUnit extension stops it after the class finishes, yet Spring TestContext retains an `ApplicationContext` and `RestClient`/datasource beans pointing to **the stopped container's address**.

Symptoms:
- Test A passes alone; in the full suite, Test B connects to the old port.
- `@DynamicPropertySource` declared on a superclass is reused across subclasses, each spinning up a different container.
- The context cache reuses a client bean that resolved its property when container A was running.
- A container restarts so `getMappedPort` changes, while the bean was already constructed with the old URL.
- `@ServiceConnection` uses a container lifecycle out of sync with the context scope.

Remedies:
1. Keep containers alive **at least as long as the context** using their URLs whenever contexts are shared.
2. Use a properly scoped container across the suite or separate `ApplicationContext`s per actual configuration.
3. When dynamic endpoints change across classes sharing a base configuration, consider `@DirtiesContext` to force a fresh context.
4. Never apply `@DirtiesContext` everywhere by default: it inflates bootstrap time and is not a way to clean database rows.
5. If a test intentionally restarts a container, rebuild URL-dependent clients/configs instead of keeping stale beans.

**Rule:** Even though `@DynamicPropertySource`'s `Supplier` is lazy, once Spring constructs `EchoGateway` with a concrete `baseUrl`, subsequent container port changes **do not rewrite the `RestClient`** inside that bean.

## 14. Common errors and how to diagnose them

| Symptom | Very common cause | Check and fix |
|---|---|---|
| `Connection refused: localhost:5678` | Using internal port on the host instead of mapped port | `getHost()+getMappedPort(5678)` |
| `getMappedPort` throws `IllegalStateException` | Called before container started | Put URL inside a supplier/lifecycle running after start |
| `getMappedPort(5678)` has no binding | Forgot `withExposedPorts(5678)` or wrong internal port | Declare exposed port and verify server really listens there |
| `http://localhost:5678` from an app container fails | `localhost` refers to the app container itself | Network alias `echo-service:5678` on the same network |
| `UnknownHostException: echo-service` | App/test JVM outside Docker network or on a different network | Check client location; attach to same network or use host mapping |
| TCP port open yet HTTP 503 | Service not ready or upstream config broken | `Wait.forHttp` / health endpoint and service logs |
| `Wait.forHttp` timeout | HTTP server failed to bind, wrong route/status, or networking | Inspect container logs, port binding, and health path |
| HTTP client uses `getMappedPort` inside an app container | Confusing host port with internal port | Use alias + internal port when sharing a network |
| Another container resolves alias yet connection is refused | Server binds only `127.0.0.1` inside service container | Bind `0.0.0.0:<internalPort>` to accept network clients |
| Passes locally, fails in CI on localhost | Different Docker host/runner container/remote daemon | `getHost()`, CI network topology, firewalls/proxies |
| `@DynamicPropertySource` has no effect | Wrong property key, broken supplier, or bean ignores property | Inspect `Environment`, bean constructor/config |
| `server.port` set to backend's mapped port | Mixing app listener with downstream service | Use a dedicated `demo.echo.base-url` property |
| Test has `ServiceConnection` yet URL config is ignored | `ConnectionDetails` takes precedence over properties | Choose one configuration source explicitly |
| PostgreSQL host test fails connecting to 5432 | Using container internal port from host | `postgres.getJdbcUrl()` |
| App container fails connecting to PostgreSQL via `getJdbcUrl` | JDBC URL holds host-mapped endpoint unsuitable for containers | `jdbc:postgresql://postgres-db:5432/db` on shared network |
| Kafka bootstrap connects yet consumer fails | Advertised listeners unreachable from client | Use module getter/service connection matching topology |
| `Connection refused` across multi-class suite | Container stopped while Spring context cache held old URL | Align lifecycle/context or use `@DirtiesContext` as needed |
| Port conflict during parallel tests | Shared fixed host ports | Let Testcontainers assign random mapped ports |
| `SSLHandshakeException` despite good TCP reachability | Scheme, cert hostname/CA/truststore mismatch | Configure HTTPS/TLS properly; never disable verification |
| Container → host URL fails to connect | Missing `exposeHostPorts` or called too late | Start host server first, expose port before starting container |
| Duplicate Docker network aliases | DNS resolves ambiguously across targets | Assign unique aliases per network/test |
| Wrong address under Docker Compose | Confusing container name, service name, and host port | Use Compose service DNS + internal port |
| Test "passes" without calling backend | Only asserted `container.isRunning()` or mocked `RestClient` | Invoke real path through Spring app and assert downstream payload |

### 14.1. A short, reliable debug sequence

When seeing `Connection refused`:

1. Identify **where the client runs**: host test JVM, JVM inside Docker, app container, or CI runner container.
2. Identify **which port and interface** the service listens on inside the container.
3. If host → container: verify `withExposedPorts`, container started, `getHost`, and `getMappedPort` at connection time.
4. If container → container: verify both share the user-defined network, alias, and internal port.
5. If container → host: verify host server started first, `exposeHostPorts` ran before client start, and hostname is `host.testcontainers.internal`.
6. Verify readiness at the protocol level, not merely `isRunning()`.
7. Separate DNS failures, TCP failures, HTTP errors, auth errors, and assertion mismatches.
8. Inspect which actual Spring property resolved into the bean; check `@ServiceConnection`/dynamic property precedence.
9. Check context cache lifecycles and container restarts when failures appear only in the full suite.
10. Never "fix" mapping errors by opening fixed ports `5432/8080` across all CI hosts; that causes races and security exposure.

## 15. Security notes and test environment design

Port mapping **opens a network access path**. Never assume every test container is safely exposed on public networks.

- Expose only **necessary** ports from containers; avoid publishing unused database/admin ports.
- Use test-only accounts/passwords and isolated databases/schemas.
- When `getHost()` points to a remote host, review Docker host security groups/firewalls; never log secrets.
- Unauthenticated HTTP services belong strictly to isolated test environments; never ship that configuration to production.
- Use dedicated Docker networks for tests when restricting container reachability.
- If tests must send outbound traffic outside controlled environments, enforce allowlists and never feed production endpoints into dynamic property sources.
- When services use HTTPS/mTLS, test CA, hostnames, truststores, and certificate rotation as part of the contract.
- Never rely on `Network.newNetwork()` to guarantee **zero** external egress: Docker containers can still have outbound access depending on host network/runtime setup.
- Clean up containers/networks at test end and monitor for leaks if CI jobs are killed.

**Distinguish network isolation from data isolation:** a PostgreSQL database in its own container makes tests steadier, yet if tests share one container and schema they still need rollback/cleanup/unique IDs. Network aliases do not clean database rows.

## 16. Common reasoning mistakes to avoid

### Mistake 1: "The container uses port 5432, so the host reaches it on 5432 too"

Wrong, because `withExposedPorts(5432)` normally maps to a **random host port**. Use `container.getMappedPort(5432)` after `start()`, or `postgres.getJdbcUrl()` for JDBC.

### Mistake 2: "The container and app run on the same machine, so they share localhost"

Wrong. **Each container has its own network namespace**; `localhost` inside an app container points only to that app container. For two containers on the same Docker network, use the DNS alias/service name.

### Mistake 3: "A network alias is a global DNS name"

Wrong. Aliases only resolve inside the Docker network the containers joined. The host JVM typically cannot resolve them. Use `getHost()+getMappedPort` for host-side tests.

### Mistake 4: "Mapped ports are fixed properties of the image"

Wrong. Images define only internal metadata; port mappings are allocated at runtime. Mappings change on restart; never save host ports in source code or immutable config.

### Mistake 5: "A running container means the backend is ready"

Wrong. The service may not be listening or initialized yet. Use a protocol-appropriate wait strategy and assert real requests.

### Mistake 6: "`@ServiceConnection` works on every endpoint"

Wrong. Boot needs a connection details factory recognizing that service. For a custom HTTP echo URL, use `@DynamicPropertySource` or explicit configuration.

### Mistake 7: "If it passes on the host, the containerized app is guaranteed to connect"

Wrong. The URL for a Spring app on the host and for a Spring app **inside a container** can be completely different. Test the actual runtime topology.

## 17. Checklist before finishing network and URL tests

- [ ] Identified whether the process **actually opening the socket** lives in the test JVM, an app container, or a host service.
- [ ] Know which internal port and binding interface the server listens on.
- [ ] For JVM → container, declared `withExposedPorts(INTERNAL_PORT)` and started the container before reading mappings.
- [ ] Used `getHost()` and `getMappedPort(INTERNAL_PORT)` without hardcoding `localhost` or host ports.
- [ ] For container → container, both containers share a network and use proper network aliases.
- [ ] Internal URLs use **alias + internal port**, never the host-mapped port.
- [ ] For container → host, the host server started first and `Testcontainers.exposeHostPorts(localPort)` ran before starting the client container.
- [ ] `@DynamicPropertySource` registers a **supplier** under the exact property key consumed by the HTTP/JDBC/Redis client.
- [ ] Did not confuse the app's `server.port`/`@LocalServerPort` with the backend service's port.
- [ ] When using `@ServiceConnection`, checked factory matching and `ConnectionDetails` precedence.
- [ ] For PostgreSQL, picked `getJdbcUrl()` for the test JVM or `alias:5432` for an app container.
- [ ] For Kafka, verified advertised listeners are reachable from the client.
- [ ] Configured a readiness wait strategy instead of guessing with `Thread.sleep`.
- [ ] Tests actually call the service and assert **status/body/DB queries**, not merely `isRunning()`.
- [ ] Container lifecycle aligns with Spring context caching; no references to stopped containers remain.
- [ ] In CI/remote Docker, handled host/bridge/proxy/firewall routing instead of forcing `localhost`.
- [ ] Parallel tests avoid fixed host ports, colliding aliases, and uncleaned shared test data.
- [ ] No leaked credentials or exposed production ports; tests run in an isolated environment.
- [ ] Executed the proper test task and inspected actual JUnit reports before claiming runtime PASS.

## 18. Standard references

- [Testcontainers Java — Networking and communicating with containers](https://java.testcontainers.org/features/networking/): `withExposedPorts`, `getMappedPort`, `getHost`, host port forwarding, and network aliases.
- [Testcontainers Java — JUnit 5 Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): `@Testcontainers`, `@Container`, static/instance lifecycle.
- [Testcontainers Java — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/): HTTP/port/log/health waiting strategies.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): lazy suppliers, precedence, and context caching.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, connection details, and Testcontainers integration.
- [HashiCorp http-echo image](https://hub.docker.com/r/hashicorp/http-echo/tags): image tag `1.0.0`, command flags `-listen`/`-text`.
- [Docker — Bridge network driver](https://docs.docker.com/engine/network/drivers/bridge/): user-defined networks and service DNS.
- [Docker — Publishing container ports](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/): difference between container internal ports and published host ports.

**Conclusion:** A service's address always depends on **where the application or test client actually executes**. A JVM outside containers uses `getHost()+getMappedPort(internal)`; an app container on the same network uses `network alias+internal port`; a container calling a host service uses `host.testcontainers.internal` after `Testcontainers.exposeHostPorts`. Spring Boot must receive the right URL via `@DynamicPropertySource` or a matching service connection once the container is started and ready. Trustworthy tests perform **real requests/DB operations**, assert results, and align container lifecycles with the Spring context — never merely asserting `isRunning()` or hardcoding `localhost`.