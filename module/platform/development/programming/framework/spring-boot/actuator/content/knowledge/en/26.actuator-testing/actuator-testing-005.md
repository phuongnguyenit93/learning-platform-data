# Choosing MockMvc, WebTestClient, or an HTTP Client Based on the Infrastructure to Verify

A test returning 200 for `GET /actuator/health` might verify that Spring handles a mock request properly, or it might verify that a real server is responding over HTTP. The verification scope is determined by **how the test delivers the request to the application**. Choose the connection approach based on the fault you need to detect.

## Choosing by Verification Boundary

| Infrastructure to Verify | Connection Approach | What the Test Exercises |
| --- | --- | --- |
| Routing, Actuator configuration, status codes, JSON, and loaded filters in a Spring MVC app | `@SpringBootTest` with mock web environment, `@AutoConfigureMockMvc`, and `MockMvc` | Spring MVC inside the test process, via mock Servlet requests and responses. |
| Request processing of a Spring WebFlux app, with reactive configuration loaded | `WebTestClient.bindToApplicationContext(context)` | The WebFlux processing chain with mock requests and responses. |
| Using the same `WebTestClient` assertion syntax to test Spring MVC | `MockMvcWebTestClient.bindTo(mvc)` | The same mock infrastructure as `MockMvc`. |
| Application port, separate management port, or embedded web server behavior over real connections | `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client, such as JDK `HttpClient`, `TestRestTemplate`, or `WebTestClient.bindToServer()` | The client connects to the server listening on the allocated port. |
| DNS, TLS, proxy routing, or access permissions from the deployment network | An HTTP client calling the deployed environment's URL from an appropriate network location | The actual components along the request path, including proxies or ingress if the URL traverses them. |

For Actuator, load the configuration that includes the real endpoints. `@SpringBootTest` creates the full Boot context. A `@WebMvcTest` only loads the selected MVC slice, while `standaloneSetup` and `bindToController` configure only the explicitly specified components. If the goal is to verify Actuator auto-configuration, use a context that includes that configuration.

When testing authorization with `MockMvc`, keep the security filters loaded and verify that the test passes through the intended filter chain. If the test attaches a mock identity, the result verifies the authorization rules for that identity. To verify real authentication, send credentials via the mechanism that real clients will use.

## Spring Boot 3.3 and Java 17 Example

The two baseline test cases use the same path `GET /ops/health`. The first verifies the HTTP and JSON contract in Spring MVC. The second starts the application server and the management server on two random ports, then checks the result when calling each port.

Create `pom.xml` in the project directory.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>demo.actuatortest</groupId>
    <artifactId>actuator-client-demo</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Create `src/main/java/demo/actuatortest/ActuatorTestApp.java`.

```java
package demo.actuatortest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorTestApp {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorTestApp.class, args);
    }
}
```

Create `src/test/java/demo/actuatortest/ActuatorMvcTest.java`. The file contains two top-level test classes. Maven picks up both classes because both class names end with `Test`.

```java
package demo.actuatortest;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "management.endpoints.web.base-path=/ops")
@AutoConfigureMockMvc
class ActuatorMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthContractInMvc() throws Exception {
        mvc.perform(get("/ops/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}

@SpringBootTest(webEnvironment = RANDOM_PORT, properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=0",
        "management.endpoints.web.base-path=/ops"
})
class ActuatorPortTest {
    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    ObjectMapper json;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    void healthIsServedOnTheManagementPort() throws Exception {
        assertNotEquals(appPort, managementPort);

        var management = getHealth(managementPort);
        assertEquals(200, management.statusCode());
        assertEquals("UP", json.readTree(management.body()).path("status").asText());

        var application = getHealth(appPort);
        assertEquals(404, application.statusCode());
    }

    private HttpResponse<String> getHealth(int port) throws Exception {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/ops/health"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return http.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
```

Run from the directory containing `pom.xml`.

```bash
mvn test
```

When running the two baseline cases, the Surefire summary reports the following counts.

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

`ActuatorMvcTest` shows that `management.endpoints.web.base-path=/ops` is applied and the endpoint returns `status=UP`. `ActuatorPortTest` additionally verifies two distinct ports, HTTP 200 and JSON on the management port, and HTTP 404 on the application port. Status 404 is expected for the sample application on this path. Applications with different security or routing rules may return another code on the application port.

## Using WebTestClient in the Same Lab

To run an optional test case through the MockMvc bridge, add the following dependency inside the `dependencies` section of `pom.xml`. The `test` scope provides the WebFlux client classes for the test. The sample application still runs Spring MVC.

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <scope>test</scope>
</dependency>
```

Create `src/test/java/demo/actuatortest/ActuatorWebTestClientTest.java` and rerun `mvn test` to execute the additional case below.

```java
package demo.actuatortest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

@SpringBootTest(properties = "management.endpoints.web.base-path=/ops")
@AutoConfigureMockMvc
class ActuatorWebTestClientTest {
    @Test
    void healthContractUsingWebTestClient(@Autowired MockMvc mvc) {
        var client = MockMvcWebTestClient.bindTo(mvc).build();

        client.get().uri("/ops/health").exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.status").isEqualTo("UP");
    }
}
```

The bridge reuses the exact `MockMvc` instance configured by Boot. To test a reactive application in-process, use `WebTestClient.bindToApplicationContext(context).build()` with the WebFlux context. To test a real connection, use `WebTestClient.bindToServer().baseUrl(...)` and choose a URL pointing to the management port or deployment address to verify. The `expectStatus()` and `expectBody()` syntax can be used in both modes.

## Interpreting Failures by Test Scope

- **Mock test passes but management port call fails.** Check the port, listening address, management server base path, endpoint exposure configuration, and HTTP or HTTPS protocol. For random ports, obtain the value from `@LocalManagementPort` instead of hardcoding a port.
- **Local HTTP test passes but deployed environment returns errors.** Test against the deployed URL and from the right network location. Local tests verify the path to the embedded server inside the test process. DNS, certificates, proxies, network rules, or authentication policies in the deployed environment require checks along the corresponding route.
- **Need to investigate both payload and infrastructure.** Keep multiple mock tests for JSON variants, statuses, and access permissions. Use a small set of real HTTP tests to verify what requires ports, connections, or a real server.

Official documentation. [Testing Spring Boot 3.3 Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) · [Configuring Management Path and Port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html) · [WebTestClient Binding Options](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
