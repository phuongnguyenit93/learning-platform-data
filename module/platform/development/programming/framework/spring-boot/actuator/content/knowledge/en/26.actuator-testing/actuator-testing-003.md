# Testing Endpoints via @SpringBootTest and a Real Web Environment

A `HealthIndicator`'s `health()` method can return `UP` when called directly, while monitoring still encounters `404`. Between those two points lie the management port, base path, list of endpoints exposed over HTTP, and security filters. Testing with `@SpringBootTest(webEnvironment = RANDOM_PORT)` verifies what callers actually observe after Spring Boot starts the embedded server and receives requests over HTTP.

## Choosing the Environment Based on the Fault to Detect

| `@SpringBootTest` Environment | HTTP Server | Use When Testing |
| --- | --- | --- |
| `MOCK`, default | Mock web environment. | Request handling inside the context with tools like `MockMvc`, if configured. |
| `RANDOM_PORT` | Real embedded server, OS-assigned port. | Listening ports, paths, HTTP endpoint exposure, filter chains, and status codes along with response bodies. |
| `DEFINED_PORT` | Real embedded server, using configured or default port. | Contracts with a specific port requirement. Concurrent runs can collide on the port. |
| `NONE` | Context without a web environment. | Beans, properties, and application-level behavior. |

With `RANDOM_PORT`, use `@LocalServerPort` to obtain the application port after the server starts. If Actuator uses a separate management server, use `@LocalManagementPort` to obtain the actual port of that server. Setting `0` in configuration requests a dynamic port. Test URLs must use the allocated port. When Actuator shares the application server, use `@LocalServerPort` for both groups of paths.

Spring Boot can provide a `TestRestTemplate` in tests with a running server. Relative URLs on the injected client target the application port. The example below passes a full `URI` so each request's destination is explicit. `TestRestTemplate` allows receiving `4xx` and `5xx` responses as a `ResponseEntity` to assert status codes directly.

## Spring Boot 3.3 Example with a Separate Actuator Port

The example creates a custom `buildcheck` endpoint using `@Endpoint` and `@ReadOperation`. The test configuration uses random ports for both servers, sets the management base path to `/ops`, and exposes exactly the two IDs `health` and `buildcheck` over HTTP. Both servers listen on the loopback address for local testing.

Create a separate Gradle project with JDK 17 or later and a Gradle version compatible with your JDK. In `settings.gradle`, set `rootProject.name = 'actuator-http-test'`. Save the three files below at the exact paths.

File `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `src/main/java/demo/actuator/ActuatorTestApplication.java`

```java
package demo.actuator;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorTestApplication {

    @Bean
    BuildCheckEndpoint buildCheckEndpoint() {
        return new BuildCheckEndpoint();
    }

    @Endpoint(id = "buildcheck")
    static class BuildCheckEndpoint {

        @ReadOperation
        public Map<String, String> read() {
            return Map.of("state", "ready");
        }
    }
}
```

File `src/test/java/demo/actuator/ActuatorHttpTest.java`

```java
package demo.actuator;

import java.net.URI;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ActuatorTestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "server.address=127.0.0.1",
                "management.server.address=127.0.0.1",
                "management.server.port=0",
                "management.endpoints.web.base-path=/ops",
                "management.endpoints.web.exposure.include=health,buildcheck"
        }
)
class ActuatorHttpTest {

    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate http;

    @Test
    void healthRespondsOnManagementPort() {
        assertJsonField("/ops/health", "status", "UP");
    }

    @Test
    void customEndpointUsesItsHttpMapping() {
        assertJsonField("/ops/buildcheck", "state", "ready");
    }

    @Test
    void infoIsNotExposedOnManagementPort() {
        ResponseEntity<String> response = http.getForEntity(
                url(managementPort, "/ops/info"), String.class);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void healthIsNotMappedOnApplicationPort() {
        assertNotEquals(applicationPort, managementPort);

        ResponseEntity<String> response = http.getForEntity(
                url(applicationPort, "/ops/health"), String.class);

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    private void assertJsonField(String path, String field, String expected) {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        ResponseEntity<JsonNode> response = http.exchange(
                url(managementPort, path), HttpMethod.GET,
                new HttpEntity<Void>(headers), JsonNode.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(contentType));
        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals(expected, body.path(field).asText());
    }

    private URI url(int port, String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }
}
```

Run from the project directory.

```bash
gradle test --tests demo.actuator.ActuatorHttpTest
```

| Test Case | Target | Expected Result and What Is Verified |
| --- | --- | --- |
| `healthRespondsOnManagementPort` | Management port, `/ops/health` | `200`, JSON has `status=UP`. Verifies the built-in endpoint goes through the configured HTTP path. |
| `customEndpointUsesItsHttpMapping` | Management port, `/ops/buildcheck` | `200`, JSON has `state=ready`. Verifies the custom endpoint's read operation is mapped to `GET`. |
| `infoIsNotExposedOnManagementPort` | Management port, `/ops/info` | `404` according to the list of endpoints exposed over HTTP in the example. |
| `healthIsNotMappedOnApplicationPort` | Application port, `/ops/health` | The two actual ports differ, and the application port returns `404` for the management path. |

In one JUnit Platform run with Java 17, Spring Boot 3.3.0, and Tomcat NIO2 on both servers, the application port was `52687` and the management port was `52688`. The result was **4 passed, 0 failed**. The port numbers only illustrate that run.

Both successful cases send `Accept: application/json` to also test content negotiation. Reading JSON with `JsonNode` and comparing contract fields keeps test cases stable when additional fields are added to the response. If consumers rely on Actuator's custom media type, send the exact `Accept` header they use and verify the corresponding `Content-Type`.

## Diagnosing Failed Tests

1. **Connection error or `404`.** Verify that the server started, the allocated port, and the actual URL sent. When sharing a port, the Actuator prefix is combined with the application's context path if configured. With a separate management server, check `management.server.base-path` and `management.endpoints.web.base-path`. Next, verify that the endpoint is enabled and exposed over HTTP. `management.endpoints.web.exposure.exclude` takes precedence over `include`.
2. **`401`, `403`, or authentication redirect.** If the application uses Spring Security, test with the same authentication mechanism used by the monitoring client. Write cases for valid permissions and denied permissions, then verify the status code against the actual configuration. For write operations via `POST`, also check the CSRF policy if the security filter chain enforces it. When verifying security policy, load that exact filter chain in the test context.
3. **`503` from health.** Read the aggregated status in JSON along with the status-to-HTTP mapping configuration. By default in Spring Boot 3.3, `DOWN` and `OUT_OF_SERVICE` map to `503`. For applications with external dependencies, supply controlled test data. For example, use a test `HealthIndicator` with a deterministic status or start a dedicated dependency for testing. Test both the healthy case and the dependency failure case if that is part of the contract to protect.
4. **Tests pass but deployment configuration differs.** The properties in the example describe a specific configuration. To test the deployment configuration, select the right profile, keep the mapping and access properties that need verification, and override only isolation values such as dynamic ports. `@SpringBootTest` defaults to `UseMainMethod.NEVER` and creates the application from configuration classes. If the application sets properties or initializers in `main`, choose the appropriate `useMainMethod` setting to include that setup in the test.

Real HTTP requests have their own server-side execution thread. If a test calls a write-operation endpoint, a transaction on the test method only wraps the test client side. Prepare data visible to the server and clean up written data explicitly. The embedded server verifies the application's HTTP contract under the loaded configuration. External layers such as ingress, TLS at a proxy, or network rules require tests from the same location that monitoring accesses.

## Reference Documentation

- [Spring Boot 3.3 · Testing Applications with a Running Server](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 · Actuator Ports and Paths over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 · Exposing Endpoints, Security, and Health Mapping](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 · TestRestTemplate API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)