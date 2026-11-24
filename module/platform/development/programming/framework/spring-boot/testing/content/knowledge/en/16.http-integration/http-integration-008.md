# Testing Management Endpoints on a Separate Port in Spring Boot

Spring Boot Actuator exposes management endpoints such as **health**, **info**, **metrics**, **loggers**, and **mappings** for monitoring, diagnostics, and operations. By default, HTTP-exposed endpoints share **the same port as the application server**. When **management.server.port** is configured differently from **server.port**, Spring Boot starts a management web server/context on a separate port.

A focused **HTTP integration test** must prove more than the presence of properties in `Environment`: **two listeners actually start, two distinct ports are assigned, the application endpoint responds on the main port, Actuator endpoints respond on the management port, and unexposed or wrong-port endpoints do not accidentally serve requests**.

This lesson uses **Java 17, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Spring MVC, and Spring Boot Actuator**. The test code uses **`@SpringBootTest(webEnvironment = RANDOM_PORT)`**, **`@LocalServerPort`**, **`@LocalManagementPort`**, and Java 17 **`HttpClient`** to send real HTTP requests. This tests **two real sockets**, unlike MockMvc. Differences for Spring Boot 4.x or secured deployments are called out clearly rather than extrapolating 3.4 behavior blindly to all versions.

## 1. Architecture: two ports, two purposes

Suppose the main server is configured on 8080 and the management server on 8081:

~~~text
                    One Spring Boot process
                              |
                  +-----------+-----------+
                  |                       |
                  v                       v
           Main server/context      Management server/context
                 :8080                    :8081
                  |                       |
          GET /api/hello           GET /actuator/health
          HTTP 200, JSON           HTTP 200, status UP
                  |                       |
    GET /actuator/health          GET /api/hello
          usually 404                usually 404
~~~

**Not two separate JVMs:** this is still one Spring Boot application, though the management listener uses a different HTTP connector/web context from the main server. Internal resources and beans can share a parent/child relationship managed by Boot; the purpose of a separate port is to **isolate HTTP serving paths**, not isolate all business faults.

**Do not confuse two ports with two paths.** If you only set `management.endpoints.web.base-path=/manage` without setting `management.server.port` differently from the main port, Actuator still serves at **`/manage/health` on the application port itself**. With a separate management port and default base path, the typical URL is **`http://host:managementPort/actuator/health`**.

**404 responses on the wrong port** in this sample are part of the minimal configuration's contract without Spring Security or custom routes. In real applications with security filters, reverse proxies, or custom controllers, hitting the wrong port might return 401, 403, a redirect, or another status. Only assert 404 when you know the routing and security rules of the target environment.

## 2. Properties controlling management HTTP

| Property | Purpose | Example value |
| --- | --- | --- |
| **server.port** | Configured port of the main web server | 8080 |
| **management.server.port** | Management port; if different from main, starts a separate listener | 8081 |
| **management.server.address** | Bind address for management server; requires separate port to differ from main | 127.0.0.1 |
| **management.server.base-path** | Base path on the separate management server | /ops |
| **management.endpoints.web.base-path** | Prefix of Actuator web endpoints, default `/actuator` | /actuator |
| **management.endpoints.web.exposure.include** | Endpoint IDs exposed over HTTP | health,info |
| **management.endpoints.web.exposure.exclude** | Excluded endpoint IDs; exclude wins over include | beans,env |
| **management.endpoint.health.show-details** | Policy for exposing detailed health info | never |
| **management.info.env.enabled** | Exposes `info.*` properties in `InfoEndpoint` when contributor active | true |
| **management.server.port=-1** | Disables HTTP management endpoints | -1 |

An endpoint can **exist in the context** without being exposed over HTTP. Conversely, exposure does not replace authentication/authorization. With Actuator, default HTTP exposure is limited (usually just `health`); never enable wildcard **`include=*`** recklessly, especially for `env`, `heapdump`, `configprops`, or `loggers`.

### Configured property value and actual runtime port are different

When you set **`management.server.port=8081`**, `8081` is the requested configuration; in a **`RANDOM_PORT`** test, Spring Boot overrides it to allocate a different random port. Therefore, tests must use:

- **`@LocalServerPort`** in package **`org.springframework.boot.test.web.server`** to obtain **`local.server.port`**, the actual bound port of the main server.
- **`@LocalManagementPort`** in the same package to obtain **`local.management.port`**, the actual bound port of the management server when it has a separate listener.
- Using **`@Value`** to read **`management.server.port`** only reads config properties and is unreliable for building URLs to a runtime random management port.

Spring Boot 3.4 docs explicitly state: **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** also gives the management server its own **separate random port** when the application configures a management port distinct from the main port. The example declares **8080 and 8081** in `application.yml`, then retrieves runtime ports via annotations. Do not merely set **`server.port=0`** and **`management.server.port=0`** and assume two independent listeners are guaranteed across every version.

## 3. Choosing the right test level

| Test type | Real HTTP listeners? | Proves separate management port? |
| --- | --- | --- |
| Unit test reading `Environment` | No | No |
| `MockMvc` in a web slice | No | No |
| Default `@SpringBootTest` `MOCK` | No | No |
| `@SpringBootTest` with `@AutoConfigureMockMvc` | No network socket serving MockMvc | No |
| `@SpringBootTest` with `webEnvironment=RANDOM_PORT` | Yes, OS-assigned ports | **Yes**, when requests hit both ports |
| `@SpringBootTest` with `webEnvironment=DEFINED_PORT` | Yes, configured/default ports | Yes, but prone to port conflicts in CI |

**MockMvc** is great for verifying Spring MVC mappings/filters/serialization without a real server. However, when the requirement is specifically a **separate port**, a passing MockMvc-only test does not prove management sockets, bind addresses, deployment routing, or TCP connections.

A valuable test needs **positive assertions** (main API and management health/info work) and **negative assertions** (wrong-port routes and unexposed endpoints fail) per contract. Never assert only that two config properties have different integers.

## 4. Runnable project: Spring Boot 3.4.5 + Actuator

Concrete contract of the example:

1. Main server configured on 8080; `GET /api/hello` returns status 200 and JSON with **`message=hello`**.
2. Management server configured on 8081, bound to **`127.0.0.1`**, exposing only **`health`** and **`info`**.
3. `GET /actuator/health` on the management port returns 200 and JSON **`status=UP`** when default health contributors are healthy.
4. `GET /actuator/info` on the management port returns 200 and property **`app.name=dual-port-demo`**.
5. `GET /actuator/health` on the main port and `GET /api/hello` on the management port return 404 in this demo setup.
6. `GET /actuator/env` on the management port returns 404 because it is not exposed.
7. Under **`@SpringBootTest(RANDOM_PORT)`**, all URLs use the actual runtime ports, **never hardcoded 8080/8081**.
8. A second test changes **`management.endpoints.web.base-path`** to verify the new path on the right management listener.

The demo app omits DBs, brokers, remote clients, and Spring Security so health/outputs remain deterministic. In real projects with external dependencies, health can be `DOWN`/`OUT_OF_SERVICE` mapped to HTTP 503; never hardcode `UP` for systems intentionally tested in degraded states.

### 4.1. Directory tree

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/managementports/DualPortApplication.java
src/main/java/com/example/managementports/HelloController.java
src/test/java/com/example/managementports/ManagementPortHttpTest.java
src/test/java/com/example/managementports/ManagementBasePathHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-dual-management-port'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`spring-boot-starter-web`** provides the embedded Servlet container and JSON support (Jackson). **`spring-boot-starter-actuator`** provides management endpoints and auto-configuration. **`spring-boot-starter-test`** provides JUnit Jupiter and Spring test support. Java **`HttpClient`** is built into Java 17, needing no extra HTTP test client dependency.

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info
  info:
    env:
      enabled: true
  endpoint:
    health:
      show-details: never

info:
  app:
    name: dual-port-demo
~~~

When running `bootRun`, the app and management listeners use configured ports 8080/8081, with management bound to loopback only. In `RANDOM_PORT` tests, Boot starts the embedded servers using random-port semantics and the **`@Local*Port` annotations** reflect the actual allocated ports.

Setting **`show-details: never`** reduces exposed health details. **`include: health,info`** is an HTTP exposure allowlist, not a substitute for security or network policies. **`management.info.env.enabled=true`** lets `info.*` properties appear in `InfoEndpoint`. Because the demo adds no Spring Security, tests call exposed endpoints without tokens; real systems must verify authorization policies separately.

### 4.2. Application and main controller

**src/main/java/com/example/managementports/DualPortApplication.java**

~~~java
package com.example.managementports;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualPortApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualPortApplication.class, args);
    }
}
~~~

**src/main/java/com/example/managementports/HelloController.java**

~~~java
package com.example.managementports;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public Message hello() {
        return new Message("hello");
    }

    public record Message(String message) {
    }
}
~~~

This controller provides a small business endpoint, enough to prove the **main server** returns HTTP 200/JSON. Because it is registered only in the main application web context, it is **not expected to appear on the management port** in this example. Jackson in Spring MVC serializes the `Message` record automatically.

## 5. Real HTTP integration test with two ports

**src/test/java/com/example/managementports/ManagementPortHttpTest.java**

~~~java
package com.example.managementports;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ManagementPortHttpTest {
    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private HttpResponse<String> get(int port, String path)
            throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + path);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private JsonNode json(HttpResponse<String> response)
            throws Exception {
        return mapper.readTree(response.body());
    }

    @Test
    void allocatesDifferentRuntimePorts() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);
    }

    @Test
    void mainApiWorksOnApplicationPort() throws Exception {
        HttpResponse<String> response =
                get(applicationPort, "/api/hello");

        assertEquals(200, response.statusCode());
        assertEquals("hello",
                json(response).path("message").asText());
    }

    @Test
    void actuatorHealthWorksOnManagementPort()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/health");

        assertEquals(200, response.statusCode());
        assertEquals("UP",
                json(response).path("status").asText());
    }

    @Test
    void actuatorInfoWorksOnManagementPort()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/info");

        assertEquals(200, response.statusCode());
        assertEquals("dual-port-demo",
                json(response).path("app")
                        .path("name").asText());
    }

    @Test
    void wrongPortDoesNotServeTheOtherRoute()
            throws Exception {
        HttpResponse<String> mainActuator =
                get(applicationPort, "/actuator/health");
        HttpResponse<String> managementApi =
                get(managementPort, "/api/hello");

        assertEquals(404, mainActuator.statusCode());
        assertEquals(404, managementApi.statusCode());
    }

    @Test
    void environmentEndpointIsNotExposed()
            throws Exception {
        HttpResponse<String> response =
                get(managementPort, "/actuator/env");

        assertEquals(404, response.statusCode());
    }
}
~~~

### Interpreting assertions by level of evidence

**`allocatesDifferentRuntimePorts`** checks **both actual post-startup values**, rather than merely comparing YAML 8080/8081. If the management server did not start separately, `@LocalManagementPort` fails injection early — which is a useful signal because a separate port is required.

**`mainApiWorksOnApplicationPort`** verifies the main HTTP listener, controller route, and JSON serialization. If the port opens yet the route fails, the test catches it, complementing the port check.

**`actuatorHealthWorksOnManagementPort`** verifies the management listener, Actuator endpoint exposure, and health body. In a minimal setup with no failing external dependencies, expecting `UP` is appropriate; do not extrapolate this into claiming production readiness is always `UP`.

**`actuatorInfoWorksOnManagementPort`** verifies both HTTP exposure of `info` and the info contributor reading `app.name`. If **`management.info.env.enabled=true`** is removed, the endpoint can still return 200 without `app.name` in the body; this test catches that regression.

**`wrongPortDoesNotServeTheOtherRoute`** confirms bidirectional route isolation. In a demo without Spring Security or custom mappings, 404 is expected. When security enforces auth, test 401/403 separately rather than inferring from this same fixture.

**`environmentEndpointIsNotExposed`** confirms the sensitive `env` endpoint is not exposed over HTTP under the allowlist. If config changes `include` to a wildcard, this test goes red instead of silently exposing another admin endpoint.

### Why use absolute URIs to the exact management port?

Some Spring Boot test clients under `RANDOM_PORT` default their base URL to the **main application port**. Calling a relative `/actuator/health` path without targeting the management base URI can accidentally hit the main port and make Actuator look broken. `HttpClient` in the example always specifies host `127.0.0.1`, an **explicit port**, and an **explicit path**.

You can swap `HttpClient` for `TestRestTemplate` or `WebTestClient` as appropriate for your Boot version, as long as you manage **two separate base URLs** and avoid reusing the main root URI for management endpoints.

## 6. Second test: non-default management base path

Management endpoint URIs have distinct parts that must not be confused:

- **`management.server.base-path`**: base path of the management server when running on a separate port.
- **`management.endpoints.web.base-path`**: prefix of web actuator endpoints, defaulting to `/actuator`.
- **`management.endpoints.web.path-mapping.<id>`**: overrides the path segment of a specific endpoint.
- **`server.servlet.context-path`**: context path of the main application servlet; does not automatically apply to a separate management server.

Changing **`management.endpoints.web.base-path=/manage`** normally moves health from **`/actuator/health`** to **`/manage/health`** on the management port. The example below tests this directly using a second test context. Because the two test classes have different configurations, Spring TestContext caches two separate contexts/servers.

**src/test/java/com/example/managementports/ManagementBasePathHttpTest.java**

~~~java
package com.example.managementports;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@SpringBootTest(
        webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = "management.endpoints.web.base-path=/manage")
class ManagementBasePathHttpTest {
    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private int getStatus(int port, String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }

    @Test
    void newManagementPathDoesNotChangeMainApi()
            throws Exception {
        assertNotEquals(applicationPort, managementPort);

        assertEquals(200,
                getStatus(managementPort, "/manage/health"));
        assertEquals(404,
                getStatus(managementPort, "/actuator/health"));
        assertEquals(200,
                getStatus(applicationPort, "/api/hello"));
        assertEquals(404,
                getStatus(applicationPort, "/manage/health"));
    }
}
~~~

**Common mistake:** you cannot mutate an `Environment` property between two JUnit test methods and expect startup-bound management MVC mappings to update dynamically. Use **`@SpringBootTest(properties=...)`** to configure **before context initialization**, then verify URLs after listeners bind. When a test needs a different base path, that is a **different context configuration**, not just a different assertion.

If you set both **`management.server.base-path=/ops`** and **`management.endpoints.web.base-path=/actuator`**, under separate-port servlet management semantics, the expected health path is **`/ops/actuator/health`**. Never mistakenly prepend the main app's context path onto management URLs. Always verify the behavior of your application's web stack and Boot version.

## 7. Run commands, expected responses, and limitations

Set up a Gradle Wrapper compatible with Java 17 and Spring Boot 3.4.x, then run from the project directory:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.managementports.ManagementPortHttpTest
./gradlew test --tests com.example.managementports.ManagementBasePathHttpTest
~~~

On Windows, use **`gradlew.bat`** instead of **`./gradlew`**. With the code/dependencies/configuration in this lesson, the tests are **designed to PASS**. This is the **expected outcome from the example's logic**, not an observed build transcript; random ports are OS-assigned, so no fixed pair of ports is listed for test output.

When running the app via:

~~~bash
./gradlew bootRun
~~~

With unmodified YAML, configured ports are **8080** and **8081**. From the same machine you can manually call:

~~~bash
curl -i http://127.0.0.1:8080/api/hello
curl -i http://127.0.0.1:8081/actuator/health
curl -i http://127.0.0.1:8081/actuator/info
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8081/api/hello
curl -i http://127.0.0.1:8081/actuator/env
~~~

| URL under YAML `bootRun` | Expected status | Meaning |
| --- | --- | --- |
| 8080/api/hello | 200 | Main MVC endpoint |
| 8081/actuator/health | 200 | Management health, JSON status `UP` |
| 8081/actuator/info | 200 | Info contributor `app.name` |
| 8080/actuator/health | 404 | Management endpoint not on main port |
| 8081/api/hello | 404 | Main API not mapped on management context |
| 8081/actuator/env | 404 | `env` endpoint not exposed |

If a fixed port is already occupied, `bootRun` can fail with **`BindException`**; that is not a failure in the HTTP test content. `RANDOM_PORT` allocates free ports safely instead of probing a socket, closing it, and hoping nobody steals it in between.

## 8. MockMvc, TestRestTemplate, and wrong-port mistakes

Three easy ways tests reach false conclusions:

**(1) Reading only the configuration property.** Asserting that `Environment` holds `management.server.port=8081` does not prove a server is actually listening there. Use runtime `@LocalManagementPort` and HTTP GET.

**(2) Treating MockMvc as socket proof.** MockMvc simulates servlet requests/dispatches. Even when autowired in `@SpringBootTest` with `@AutoConfigureMockMvc`, requests do not traverse two separate TCP listeners. It can test handlers in the right context, but it is not a test of network port isolation.

**(3) Using a test client bound to the main server's base URL.** A relative path `/actuator/health` when the management port is separate can go to the main port and receive 404. Build URLs with the actual `managementPort`; for other clients, configure separate base URIs or absolute URLs explicitly.

**Do not use `@LocalManagementPort` unconditionally.** When management does not use a separate port or HTTP management is disabled, `local.management.port` may not exist. This annotation is for real-server tests with an allocated management listener port. If testing Actuator on the main port, use `@LocalServerPort` and adjust assertions accordingly.

## 9. Security, endpoint exposure, and 401/403 statuses

Splitting ports creates a **separate access path**; it is not automatically authentication, authorization, or a firewall. In real applications:

- **`management.endpoints.web.exposure.include`** determines which endpoints are exposed over HTTP. Use an allowlist and avoid public wildcards.
- **`management.endpoint.<id>.access`** and Boot-version access policies restrict endpoint permissions, separate from HTTP exposure.
- **Spring Security** can require authentication or roles for Actuator; if a project defines a custom `SecurityFilterChain`, default auto-config can back off, requiring explicit rules for both main and management contexts.
- **`management.server.address=127.0.0.1`** binds the listener to local loopback in network config, yet does not prove the deployment environment does not publish it via proxy, port forwarding, or sidecar.
- Management ports typically need internal network policies, TLS, and strict access limits on `/env`, `/beans`, `/heapdump`, and `/loggers` if enabled for operations.

The demo **omits `spring-boot-starter-security`**, so 200/404 are intentional fixture behavior. Once security is added, separate **exposure tests** (is the endpoint HTTP-registered?), **access tests** (which user/token may view it?), and **network tests** (which addresses can connect?). Never change expected statuses to 200 just to get green tests, nor claim 404 is always the contract in every secured app.

## 10. Management health UP does not guarantee main server readiness

Because the management server uses a separate HTTP listener and web infrastructure, it can return **health UP** even when the **main listener** is stalled, out of threads, or failing application traffic. Tests should therefore check the **main API** alongside management health, as in Section 5.

For Kubernetes deployments, Spring Boot supports **liveness/readiness health groups** and optional exposure on the main server:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

When supported and configured, health groups can also be exposed on the main port at **`/livez`** and **`/readyz`**. Health groups also support `additional-path` with **`server:`** or **`management:`** prefixes. That does not make `/actuator/health` appear on main by itself, yet it shows that claiming "every health URL exists only on the management port" can be false when **intentional additional paths** exist.

Liveness and readiness serve different contracts: do not make liveness depend on an external DB if a transient outage would trigger a restart loop. If using readiness on the main port to gate traffic, test it against real health indicators/lifecycles rather than trusting a single `UP` response for all load conditions.

## 11. Configuration variations and what to adjust in tests

| Configuration | Main behavior | How to write tests |
| --- | --- | --- |
| `management.server.port` unset | Actuator shares main port | Use `@LocalServerPort`; do not require a separate `local.management.port` |
| `management.server.port` equals `server.port` | Does not split listeners merely by setting same value | Do not assert two ports are different |
| `management.server.port` differs from `server.port` | Management gets separate listener when auto-config conditions hold | `@LocalManagementPort`, HTTP to both ports |
| `management.server.port=-1` | Disables HTTP management endpoints | Do not try injecting management port or calling HTTP health |
| `management.endpoints.web.base-path=/manage` | Changes web endpoint prefix | `GET /manage/health` on management port |
| `management.server.base-path=/ops` | Changes separate management server base path | Verify the combined management path in practice |
| Expose `include=health` | `info` is not exposed unless overridden | `/actuator/info` typically returns 404 |
| Spring Security present | Endpoints may return 401/403 if unauthorized | Test with and without credentials for matching roles |
| Probes additional paths enabled | Adds health paths on main port | Adjust negative tests to account for real allowlisted paths |

Use one clear configuration per test context. If `@SpringBootTest(properties=...)` overrides YAML, conclusions apply only to the **overridden test context**, not automatically to production config. When runtime environments inject env vars or other profiles, verify property precedence.

## 12. CI, caching, concurrent tests, and cleanup

Spring TestContext caches `ApplicationContext` instances across tests sharing equivalent configurations. Therefore:

- Two classes with identical config can share the same embedded servers/ports inside the same test JVM.
- A class overriding base path with `@SpringBootTest(properties=...)` has a different merged configuration and starts its own server/context.
- `RANDOM_PORT` avoids fixed-port collisions when parallel tests/processes run.
- Never initialize a `static final` URL before server startup; `@Local*Port` fields are unpopulated then.
- Never call `System.setProperty("management.server.port", ...)` between tests expecting a cached context to rebind its listener to a new port.
- Using `@DirtiesContext` closes the context and restarts web servers, increasing runtime.
- If using a database, `@Transactional` on a JUnit method does not roll back server-thread transactions for real HTTP calls through the embedded server. Clean up data explicitly.
- `HttpClient` connect/read timeouts prevent CI from hanging indefinitely, though timeouts do not prove production business SLAs.
- Under `DEFINED_PORT`, parallel suites binding 8080/8081 can collide and fail. Prefer `RANDOM_PORT`.

## 13. Common error table

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| `@LocalManagementPort` fails to inject | No separate management listener or no real HTTP server | Check actuator dependency, port config differing from main, and `webEnvironment` |
| `applicationPort == managementPort` | Listeners not split per config/version | Verify `management.server.port` differs from main |
| `GET /actuator/health` on main returns 404 | Called wrong port when management is separated | Switch to `managementPort` |
| Calling configured port 8081 in `RANDOM_PORT` gets refused | Runtime management port was randomized | Use `@LocalManagementPort` |
| `/actuator/health` on management returns 503 | Health indicator reports `DOWN`/`OUT_OF_SERVICE` | Inspect dependencies and health body |
| `/actuator/info` returns 200 with empty body | Info env contributor disabled or no `info.*` properties | Enable `management.info.env.enabled` and verify mapping |
| `/actuator/info` returns 404 | `info` not exposed | Check exposure allowlist |
| `/actuator/health` returns 401 or 403 | Spring Security / access policy blocks it | Test authentication/authorization per policy |
| `/actuator/env` unexpectedly returns 200 | Wildcard exposure or config override | Tighten `include`/`exclude` and security |
| `/manage/health` not found | Wrong path/port calculation, or property not overridden before startup | Test management base path with right startup config |
| Main API appears on management port | App registered custom routes/config or failed to split ports | Inspect routing and server contexts |
| MockMvc test passes while management socket fails | MockMvc uses no TCP requests | Move to a real HTTP `RANDOM_PORT` test |
| `bootRun` fails to bind port | 8080/8081 occupied or invalid bind address | Inspect network interfaces/ports; use random ports for tests |
| Management health `UP` while main traffic fails | Separate HTTP contexts can fail independently | Test main API and main readiness/liveness paths where relevant |
| Test passes alone, fails in suite | Fixed ports, context cache, shared mutable globals/state | `RANDOM_PORT`, minimize shared mutation, isolate test configs |

## 14. Counter-example exercises

**A.** App configures `main=8080`, `management=8081`. A `RANDOM_PORT` test calls `http://localhost:8081/actuator/health` and fails. Does that prove Actuator is broken? **No.** Fetch the actual `local.management.port` and call that port.

**B.** A test only asserts `management.server.port != server.port` in `Environment`. Has it tested the management HTTP listener? **No.** Config properties do not prove sockets opened or routes serve requests.

**C.** `@WebMvcTest` with `MockMvc` passes `GET /actuator/health`. Is that sufficient proof of two separate ports? **No.** `MockMvc` does not traverse two TCP listeners.

**D.** `GET /api/hello` on the main port and `/actuator/health` on the management port both return 200. Have we proven routes do not leak onto the wrong port? **No.** Negative assertions on the swapped ports are required.

**E.** Changing `management.endpoints.web.base-path` from `/actuator` to `/manage` without restarting the test context — does the endpoint update immediately? **No guarantee.** Route mappings are bound during context initialization; use a test context initialized with that property.

**F.** Management health returns `UP` while the main thread pool is exhausted and unable to serve HTTP requests. Do those two states contradict each other? **No.** A healthy management listener does not guarantee the main server is accepting traffic.

**G.** Spring Security is added and `GET /actuator/info` returns 401. Should you update the test to expect 200 without adding authentication? **No.** Tests must reflect the intended access policy.

**H.** `management.server.address=127.0.0.1` and local tests on the same host pass. Does that prove the port is unreachable from the Internet after deployment? **Not completely.** That also depends on network namespaces, gateways, proxies, and firewalls.

### Review checklist

- Are `spring-boot-starter-actuator` and the web server starter added?
- Is `management.server.port` genuinely different from `server.port` in the target config?
- Does the test use `@SpringBootTest(webEnvironment=RANDOM_PORT)` or have an explicit reason for `DEFINED_PORT`?
- Are `@LocalServerPort` and `@LocalManagementPort` retrieved after server startup?
- Does the test assert both runtime ports are positive and distinct?
- Are HTTP GETs sent to the respective ports for the main API and management health/info?
- Are response bodies/statuses asserted rather than just port binding?
- Are negative assertions present for wrong-port routes and unexposed endpoints?
- Are 401/403 security rules, auth, and hiding sensitive endpoints considered?
- Are management base path, Actuator base path, and main servlet context path calculated properly?
- When management health is `UP`, is there complementary evidence for main port / readiness when required?
- Are random ports never hardcoded and tests independent of context cache or mutable `System` properties?
- Is it clear that JUnit `@Transactional` does not roll back server-side HTTP transactions?
- Are conclusions properly scoped to the demo environment and Spring Boot version?

**Conclusion:** Testing management endpoints on a separate port is a **real HTTP integration test across two listeners**, not just checking annotations or properties. Configure `management.server.port` differently from `server.port`; run with `RANDOM_PORT` to avoid CI collisions; capture actual ports with `@LocalServerPort` and `@LocalManagementPort`; send HTTP requests to each port; and assert **positive paths, wrong-port paths, exposure, bodies, and statuses**. When an app uses security, custom paths, probes, or network isolation, add assertions matching the real policy instead of generalizing a simple health check across all of production.

## Official documentation

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Monitoring and Management Over HTTP: https://docs.spring.io/spring-boot/3.4/reference/actuator/monitoring.html
- Spring Boot 3.4 — Actuator Endpoints and Health Probes: https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html
- Spring Boot 3.4 — LocalManagementPort API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html
- Spring Boot 3.4 — LocalServerPort API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
