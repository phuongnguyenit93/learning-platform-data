# Testing Health Group Content, HTTP Status, and Authorization

A health group gathers health checks related to a single operational purpose. For example, the `orders` group aggregates only the status of components serving orders. A useful test must verify three outcomes of the same HTTP request. Who is allowed to call the group? Which HTTP status code does the client receive? Which portion of JSON is shown to that caller?

## Separating Call Authorization from Detail Visibility

- **URL call authorization** is decided by the Spring Security filter chain. In the example using HTTP Basic, requests missing credentials receive 401. Authenticated users lacking an allowed role receive 403.
- **Component and detail visibility** is enforced by Actuator for callers who are already allowed to invoke the group. `show-components` controls the `components` field. `show-details` controls `details` information, such as details inside a component. With `when-authorized`, the group's `roles` list decides who can view them. Thus, the same `UP` status can appear in two HTTP 200 responses with different bodies.
- **Health HTTP status code** is mapped from the aggregated status of the components belonging to the group. The default mapping returns 503 for `DOWN` and `OUT_OF_SERVICE`, while `UP` returns 200. Check both the HTTP status code and the `status` value in JSON. An unmapped status, such as `UNKNOWN` by default, can also return 200.

`management.endpoints.web.exposure.include=health` exposes the `health` endpoint over the web. Exposing the endpoint, filtering URL access permissions, and controlling detail visibility are three configurations that must be verified separately.

## Test Matrix for the orders Group

The group contains only `ordersBackend`. The test fixture intentionally adds an `invoicesBackend` check that always reports `DOWN` outside the group. This helps detect both accidentally calling `GET /actuator/health` and accidentally including extra components in the group.

| Caller | ordersBackend Status | HTTP | Content to Verify |
| --- | --- | --- | --- |
| Unauthenticated | `UP` | 401 | Blocked at the security layer. |
| Authenticated with role `OTHER` | `UP` | 403 | Blocked at the authorization layer. |
| Role `VIEWER` | `UP` | 200 | `status=UP`, no `components` and no `details`. |
| Role `OPS` | `UP` | 200 | Only the `ordersBackend` component with detail `check=ok`. |
| Role `OPS` | `DOWN` | 503 | `status=DOWN`, detail of `ordersBackend` is `check=unavailable`. |

## Integration Test Example

The example uses Java 17, Spring Boot 3.5.9, and Spring Security. The health group properties and HTTP status mapping rules here also apply in Spring Boot 3.3. `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts the embedded server on a random port. `TestRestTemplate` sends requests over HTTP and lets you inspect 4xx or 5xx responses directly.

Create a Maven project with the following `pom.xml`.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>
    <groupId>demo.health</groupId>
    <artifactId>health-group-demo</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Create `src/main/resources/application.properties`. In the example, both `VIEWER` and `OPS` may call the URL, whereas only `OPS` may view components and details. The server listens only on loopback.

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health
management.endpoint.health.group.orders.include=ordersBackend
management.endpoint.health.group.orders.show-components=when-authorized
management.endpoint.health.group.orders.show-details=when-authorized
management.endpoint.health.group.orders.roles=OPS
```

Create `src/main/java/demo/health/HealthGroupApp.java`. The two `HealthIndicator` beans provide deterministic test data, allowing status checks without calling dependent services. The three in-memory accounts and `{noop}` passwords are for this local lab.

```java
package demo.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthGroupApp {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupApp.class, args);
    }

    @Bean
    HealthIndicator ordersBackend(@Value("${demo.orders.up:true}") boolean up) {
        return () -> (up ? Health.up() : Health.down())
                .withDetail("check", up ? "ok" : "unavailable")
                .build();
    }

    @Bean
    HealthIndicator invoicesBackend() {
        return () -> Health.down().build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer").password("{noop}lab-only").roles("VIEWER").build(),
                User.withUsername("ops").password("{noop}lab-only").roles("OPS").build(),
                User.withUsername("other").password("{noop}lab-only").roles("OTHER").build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health/orders", "/actuator/health/orders/**")
                        .hasAnyRole("VIEWER", "OPS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Create `src/test/java/demo/health/HealthGroupTest.java`. The file contains two top-level test classes. The second class starts a separate context with `demo.orders.up=false`, so the `DOWN` state does not require mutating shared state across test cases.

```java
package demo.health;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class HealthGroupTest {
    static final String PATH = "/actuator/health/orders";
    static final String PASSWORD = "lab-only";

    @Autowired
    TestRestTemplate client;

    @Test
    void anonymousGets401() {
        var response = client.getForEntity(PATH, String.class);
        assertEquals(401, response.getStatusCode().value());
    }

    @Test
    void authenticatedWithoutRoleGets403() {
        var response = client.withBasicAuth("other", PASSWORD)
                .getForEntity(PATH, String.class);
        assertEquals(403, response.getStatusCode().value());
    }

    @Test
    void viewerGets200WithoutComponentsOrDetails() {
        var response = client.withBasicAuth("viewer", PASSWORD)
                .getForEntity(PATH, JsonNode.class);
        assertEquals(200, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());
        assertFalse(body.has("components"));
        assertFalse(body.has("details"));
    }

    @Test
    void opsGetsOnlyTheGroupsComponentAndItsDetails() {
        var response = client.withBasicAuth("ops", PASSWORD)
                .getForEntity(PATH, JsonNode.class);
        assertEquals(200, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("UP", body.path("status").asText());
        JsonNode components = body.path("components");
        assertEquals(1, components.size());
        assertEquals("UP", components.at("/ordersBackend/status").asText());
        assertEquals("ok", components.at("/ordersBackend/details/check").asText());
    }
}

@SpringBootTest(webEnvironment = RANDOM_PORT, properties = "demo.orders.up=false")
class HealthGroupDownTest {
    @Autowired
    TestRestTemplate client;

    @Test
    void unhealthyGroupReturns503AndDownBody() {
        var response = client.withBasicAuth("ops", HealthGroupTest.PASSWORD)
                .getForEntity(HealthGroupTest.PATH, JsonNode.class);
        assertEquals(503, response.getStatusCode().value());

        JsonNode body = response.getBody();
        assertNotNull(body);
        assertEquals("DOWN", body.path("status").asText());
        assertEquals("unavailable", body.at("/components/ordersBackend/details/check").asText());
    }
}
```

Run from the directory containing `pom.xml` using Maven and JDK 17 or later.

```bash
mvn test
```

When the tests pass, the Surefire summary line looks like this. Execution time and startup log lines depend on the machine.

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

The 200 and 503 cases read JSON field by field so they remain valid even when field order changes. The `VIEWER` case verifies that **the fields are genuinely absent**. The `OPS` case checks for exactly one component and its exact name, catching both data leaks and group membership misconfiguration.

## When Results Deviate from Expectations

| Result | Check Next |
| --- | --- |
| A user with the right role still receives 401 or 403 | Check credentials, actual path, rule ordering, and the roles assigned by Spring Security. With the default prefix, `roles("OPS")` grants `ROLE_OPS`. |
| `VIEWER` sees components or details | Check `show-components`, `show-details`, and `roles` at the group level individually. Also check subpaths such as `GET /actuator/health/orders/ordersBackend` if the system exposes those paths as well. |
| Passed security but the group is unreachable | Check the group name, management port, base path, and endpoint exposure configuration. If the application fails to start, verify that component names in `include` match the IDs recognized by Actuator. |
| JSON reports `DOWN` but HTTP is not 503 | Compare global mapping configuration with group-specific configuration. When configuring custom mappings, redeclare `DOWN` and `OUT_OF_SERVICE` if you still want the 503 default, then test each code in the group's contract. |

If Actuator is deployed on a separate management port, test through the actual management port. The test suite above on the shared application port verifies the path in the sample configuration. Deployments with a separate management port, proxy, or different authentication mechanism need to rerun the same matrix against the corresponding access path.

Official documentation. [Health Groups and HTTP Mapping in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Testing with a Running Server](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html) · [HTTP Authorization in Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
