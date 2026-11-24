# Using @LocalManagementPort When the Management Port Is Separated

When the application and Actuator use two different HTTP ports, tests must send requests to the right server. For example, `GET /actuator/health` may return `404` on the application port while the endpoint is active on the management port. With dynamically assigned ports, Spring Boot provides two annotations to retrieve the port numbers after the servers start. [Testing Spring Boot with a Real HTTP Server](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)

| Annotation | Runtime Property | Used to Call |
| --- | --- | --- |
| `@LocalServerPort` | `local.server.port` | The main HTTP server of the application. |
| `@LocalManagementPort` | `local.management.port` | The management server started on a separate port. |

Both annotations live in the `org.springframework.boot.test.web.server` package. `@SpringBootTest(webEnvironment = RANDOM_PORT)` tells Spring Boot to start the application server on a dynamically assigned port. Additionally set `management.server.port=0` to request a separate management server on another dynamic port. The value `0` tells the operating system to choose a port. Once the servers start, both fields are injected with the actual port numbers to build URLs. [LocalServerPort](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html) · [LocalManagementPort](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html)

## Testing Both Ports in the Same Run

The example uses Java 17 or later, Gradle, and Spring Boot 3.3.0. Create the following three files in a separate test directory. The test configuration restricts both servers to the loopback address and exposes the `health` endpoint. The sample application uses the default Actuator base path and does not add Spring Security.

**`build.gradle`**

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
    testLogging {
        events 'passed', 'failed'
    }
}
```

**`src/main/java/demo/actuator/PortsDemoApplication.java`**

```java
package demo.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortsDemoApplication.class, args);
    }
}
```

**`src/test/java/demo/actuator/SeparateManagementPortTest.java`**

```java
package demo.actuator;

import java.net.URI;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=0",
        "management.endpoints.web.exposure.include=health"
    }
)
class SeparateManagementPortTest {

    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate rest;

    @Test
    void servesHealthOnlyOnTheManagementPort() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);

        String healthPath = "/actuator/health";
        URI managementUrl = URI.create("http://127.0.0.1:" + managementPort + healthPath);
        URI applicationUrl = URI.create("http://127.0.0.1:" + applicationPort + healthPath);

        var health = rest.getForEntity(managementUrl, JsonNode.class);
        assertEquals(HttpStatus.OK, health.getStatusCode());
        JsonNode body = health.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());

        var onApplicationPort = rest.getForEntity(applicationUrl, String.class);
        assertEquals(HttpStatus.NOT_FOUND, onApplicationPort.getStatusCode());
    }
}
```

From the directory containing `build.gradle`, run the following command.

```bash
gradle test --tests demo.actuator.SeparateManagementPortTest
```

The test verifies that both ports were allocated, that the two port numbers differ, and that the same path produces two different results.

- Calling on the **management port** returns `200 OK`. The `status` field in JSON is `UP` for the healthy sample application.
- Calling on the **application port** returns `404 Not Found` because this Actuator route is mapped only on the management server. This check verifies the port separation in the sample configuration. For applications that map the same path or have custom security rules, assert the response against the application's actual contract.

Both calls pass an absolute `URI` to `TestRestTemplate`. With the client injected by `@SpringBootTest`, a relative path such as `"/actuator/health"` uses the base address of the primary server. Obtaining `managementPort` only provides the port number to construct the address. The client sends requests to the management port when the URL or base address is configured with that port.

## Diagnosing Failed Tests

| Symptom | What to Check |
| --- | --- |
| Cannot resolve `local.management.port` | Confirm there is a separate management server, with `management.server.port=0` in the test configuration. When Actuator shares the port, use `@LocalServerPort`. A value of `management.server.port=-1` disables HTTP access to endpoints. |
| Test uses `MOCK` or only MockMvc | MockMvc tests request handling through Spring MVC in-process. Choose `RANDOM_PORT` and send real HTTP requests to verify that two servers are listening on two ports. |
| Management port returns `404` | Check that the endpoint is exposed over HTTP and that the URL uses the right path. If `management.endpoints.web.base-path` was changed to `/ops`, the health path is `/ops/health`. Also check `management.server.base-path` if the application sets that property. |
| Receiving `401`, `403`, or TLS connection errors | Check authentication, access permissions, and the protocol of the management port. A separate management port may use its own SSL configuration. The annotation supplies the port number, while the client still needs the right protocol and credentials. |

When reading results, inspect the port number, path, and response status code together. A single `200` check can confirm that the endpoint works. Calling the same path across both ports verifies how management routes are separated in this example. [Actuator Port, Path, and SSL Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
