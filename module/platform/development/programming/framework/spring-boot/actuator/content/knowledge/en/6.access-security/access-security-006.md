# Designing Least-Privilege Access for Operators and Monitoring Systems

## 1. Starting from the Job to Be Done

Actuator provides access points for observing and managing a Spring Boot application. Operators need to diagnose incidents; monitoring systems need to collect signals regularly. These two needs differ, so they require different permissions.

**Least privilege** means each identity is permitted to perform only the actions required for its job, on the right data, in the right environment, and for the needed duration.

For example, a Prometheus process needs to scrape JVM metrics every 15 seconds. If you give it an Actuator admin account, should those credentials leak, the impact could go far beyond reading metrics. Conversely, an on-call operator may need to inspect component status and log level configuration, without automatically needing to change log levels or dump the entire heap.

Outline of this article:

1. Translate operational needs into an identity – endpoint – HTTP method – data detail matrix.
2. Separate enabling endpoints, exposing them over HTTP, and authorizing access.
3. Build an example with separate permissions for monitoring, operations, and the application.
4. Test both allowed access and access that must be denied.
5. Scale up with controls when moving to real environments.

Examples use **Java 21, Spring Boot 3.3.13, Spring MVC, and Spring Security 6 with versions managed by Spring Boot**. This is a fixed version for the hands-on lab in the 3.3.x line; it does not imply it is the latest version or current production deployment recommendation. The Servlet configuration below cannot be used verbatim for WebFlux.

## 2. Reading Data Is Also a Privilege

Do not only ask “who is allowed into Actuator?”. Ask four concrete questions:

- Which person or process is that identity?
- Which endpoints does it need?
- Which HTTP methods may it use?
- How much detail does it need to see?

An operation that does not mutate state can still leak system structure or consume heavy resources:

| Need | Suitable permission to consider | What should not be bundled with it |
| --- | --- | --- |
| Periodic metrics collection | Read the Prometheus endpoint | Reading full configuration or changing log levels |
| Service readiness checks | Read necessary health status | Seeing all component names, paths, and internal errors |
| Incident diagnosis | Read metrics, component status, relevant log configuration | Permanent admin rights across every endpoint |
| Deep data collection | Dedicated, approved, time-bound permission | Automatically bundled into routine “read-only” access |

For instance, a heap dump can contain business data and credentials in memory. Thus, “GET only” is still not enough to qualify as least privilege: you must also choose which resources can be read. Monitoring metrics must also be reviewed to avoid putting customer IDs, email addresses, or secrets into metric tags.

## 3. Permission Matrix Before Writing Configuration

In this hands-on lab, we design the following policy. This is one approach for a concrete scenario, not Spring Boot's default role set.

| Request | Unauthenticated | Monitoring account `monitor` | Operations account `ops` | Application account `app` |
| --- | --- | --- | --- | --- |
| GET `/actuator/health` | Deny | Aggregate status | Configured status and components/details | Deny |
| GET `/actuator/prometheus` | Deny | Permit | Deny | Deny |
| GET `/actuator/metrics` and subpaths | Deny | Deny | Permit | Deny |
| GET `/actuator/loggers` and subpaths | Deny | Deny | Permit | Deny |
| POST `/actuator/loggers/{name}` | Deny | Deny | Deny | Deny |
| GET `/api/ping` | Deny | Deny | Deny | Permit |
| All remaining endpoints | Deny | Deny | Deny | Deny |

In the `GET /api/ping` row, only the `app` account is permitted. This is a small demo API proving application permissions are separate from management permissions.

Actual list of authorities:

| Identity | Granted authorities |
| --- | --- |
| `monitor` | `ROLE_MONITOR`, `actuator:prometheus:read` |
| `ops` | `ROLE_OPS`, `actuator:metrics:read`, `actuator:loggers:read` |
| `app` | `ROLE_APP_USER` |

`ops` does not automatically inherit `monitor`'s permissions. If a person's job requires both, granting the additional authority must come from an explicit need. There is also no “admin everything” role in this example.

Permission to view health details is controlled separately: being allowed to call the endpoint does not automatically mean seeing every field in the response.

## 4. Three Layers to Distinguish

### 4.1. Enabling Endpoints, Exposing Over HTTP, and Authorizing Access

There are three independent decisions:

1. **Enable:** is the endpoint activated inside the application?
2. **Expose:** is the endpoint published over HTTP or JMX?
3. **Authorize:** is an incoming request to the endpoint allowed to execute?

In Spring Boot 3.3, use `management.endpoints.enabled-by-default`, `management.endpoint.<id>.enabled`, and `management.endpoints.web.exposure.include` for the first two layers. These properties do not replace Spring Security rules. When declaring a custom `SecurityFilterChain`, you are responsible for configuring security according to your policy. [Actuator 3.3 Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

The example will explicitly select four endpoints instead of exposing everything over HTTP. Outside that list, we also deny by default at the authorization layer. That way, adding an endpoint later will not accidentally grant permission to use it.

### 4.2. Network Boundaries and Identity

The control flow can be visualized as follows:

```text
Allowed connection source
    -> Protected transport channel
    -> Identity authentication
    -> Security chain selection
    -> Endpoint + method + permission check
    -> Data detail-level filtering
    -> Return response and record appropriate audit trail
```

An internal network reduces reachability, yet a process inside that network can still be compromised. Therefore, network restrictions and identity-based authorization complement each other.

Separating the management port is a deployment option; changing the port does not automatically authenticate callers. Spring Boot allows a separate management port and bind address; `management.server.address` only sets a separate address when the management port differs from the application port. [Management HTTP Config 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 4.3. Machine Identities and Human Identities

- Monitoring scrapers use dedicated service accounts tied to metrics collection.
- Human operators in real environments use personal identities so actions can be audited and revoked individually.
- Do not share one admin account across monitoring scrapers, on-call teams, and business APIs.
- Separate credentials across development, staging, and production.
- Emergency intervention permissions need explicit expiration and revocation mechanisms.

The two names `monitor` and `ops` in the example are a convenient simulation to run on a personal machine. In particular, `ops` here is not a recommendation for a team-wide shared account in production.

## 5. Complete Hands-On Project

Create a separate project directory with the structure:

```text
actuator-least-privilege/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/leastprivilege/
    │   │   ├── DemoApplication.java
    │   │   ├── PingController.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/com/example/leastprivilege/
        └── AccessPolicyTest.java
```

This is a Spring Boot application requiring the dependencies below; do not run individual Java files with `javac FileName.java`. Use Maven with JDK 21. The first build needs access to Maven Central.

### 5.1. Dependencies: `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-least-privilege</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
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
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

`micrometer-registry-prometheus` provides the metrics exporter needed for the Prometheus endpoint; merely listing the endpoint name in exposure does not create the missing exporter.

### 5.2. Limiting the Management Surface: `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus,metrics,loggers
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: when-authorized
      show-components: when-authorized
      roles: OPS
    prometheus:
      enabled: true
    metrics:
      enabled: true
    loggers:
      enabled: true

demo:
  monitor-password: ${MONITOR_PASSWORD}
  ops-password: ${OPS_PASSWORD}
  app-password: ${APP_PASSWORD}
```

This configuration intentionally enables and exposes four endpoints over HTTP. There is no `env`, `configprops`, `heapdump`, or `shutdown` in the policy.

Environment variables holding passwords must be set before running. Do not define default values so the application cannot accidentally start with weak passwords. Address `127.0.0.1` restricts the lab to the local machine; a monitoring scraper on another host or container cannot reach this loopback address.

Both `show-details` and `show-components` use `when-authorized`, with role `OPS`. Thus `monitor` can call health but cannot view the component tree. This visibility mechanism is a separate layer after the request-authorization decision. [Health visibility permissions in Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Disabling discovery only removes the links document at the Actuator root path; it does not replace authentication or authorization. Disabling JMX and excluding endpoints from JMX exposure ensures the example does not open an extra management channel outside HTTP. JMX mechanisms from third-party libraries or JVM launch flags must be checked separately. [Spring Boot JMX configuration scope](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 5.3. Entry Point: `DemoApplication.java`

Place the file at `src/main/java/com/example/leastprivilege/DemoApplication.java`.

```java
package com.example.leastprivilege;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.4. Demo API: `PingController.java`

Place the file at `src/main/java/com/example/leastprivilege/PingController.java`.

```java
package com.example.leastprivilege;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

### 5.5. Authorization: `SecurityConfig.java`

Place the file at `src/main/java/com/example/leastprivilege/SecurityConfig.java`.

```java
package com.example.leastprivilege;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    private static RequestMatcher getEndpoint(String id) {
        return new AndRequestMatcher(
                EndpointRequest.to(id),
                request -> HttpMethod.GET.matches(request.getMethod()));
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(getEndpoint("health"))
                    .hasAnyRole("MONITOR", "OPS")
                .requestMatchers(getEndpoint("prometheus"))
                    .hasAuthority("actuator:prometheus:read")
                .requestMatchers(getEndpoint("metrics"))
                    .hasAuthority("actuator:metrics:read")
                .requestMatchers(getEndpoint("loggers"))
                    .hasAuthority("actuator:loggers:read")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        // Keep default CSRF; no write operations are authorized.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/ping")
                    .hasRole("APP_USER")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.monitor-password}") String monitorPassword,
            @Value("${demo.ops-password}") String opsPassword,
            @Value("${demo.app-password}") String appPassword) {
        var monitor = User.withUsername("monitor")
                .password(encoder.encode(monitorPassword))
                .authorities("ROLE_MONITOR", "actuator:prometheus:read")
                .build();
        var ops = User.withUsername("ops")
                .password(encoder.encode(opsPassword))
                .authorities("ROLE_OPS", "actuator:metrics:read",
                        "actuator:loggers:read")
                .build();
        var app = User.withUsername("app")
                .password(encoder.encode(appPassword))
                .authorities("ROLE_APP_USER")
                .build();
        return new InMemoryUserDetailsManager(monitor, ops, app);
    }
}
```

### 5.6. Reading the Configuration Following the Request Flow

**Select the chain first, then select the rule.** The `@Order(1)` chain only receives requests matching Actuator endpoints. The `@Order(2)` chain has no `securityMatcher` restriction, so it covers all remaining requests. Spring Security picks the first matching chain; a request that enters the Actuator chain and is denied will not proceed to the application chain to request permission again. A fallback chain covering the rest is needed when configuring multiple chains yourself. [Multiple security filter chains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances).

**Combine conditions with AND.** The `getEndpoint("loggers")` helper requires both matching the loggers endpoint location and being a GET method. Then the rule checks `actuator:loggers:read`. As a result, the same `ops` account can read log levels but cannot change log levels.

`EndpointRequest` relies on endpoint locations managed by Actuator, reducing dependence on hardcoded path strings when changing prefixes. `toAnyEndpoint()` also includes the links endpoint if discovery is enabled. [EndpointRequest 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

**Deny by default.** There is no line saying “authenticated users can view all of Actuator”. An endpoint enabled later still requires a matching allow rule. Rules in order use the first match, so specific permissions come before `anyRequest().denyAll()`. [Spring Security 6.3 Authorization Rules](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/docs/modules/ROOT/pages/servlet/authorization/authorize-http-requests.adoc).

**Roles and granular authorities do not share the same syntax.** `hasRole("OPS")` checks the `ROLE_OPS` authority using the default prefix convention. `hasAuthority("actuator:metrics:read")` checks the exact declared authority string. Do not use `hasRole("ROLE_OPS")` or assume a role implicitly carries every granular authority.

**Open only the HTTP methods actually needed.** The example intentionally grants only GET, without automatically granting HEAD, OPTIONS, or POST. If a real tool uses HEAD, put that requirement into the matrix and test it separately. Add permissions per specific task, avoiding opening all methods for convenience.

**Keep CSRF protection.** No write operations are permitted, so the example keeps default CSRF configuration. A 403 on a POST missing a token may come from CSRF before authorization checks. The test below adds a valid token to prove that changing log levels is still denied at the authorization layer. HTTP Basic and choosing stateless sessions are not enough by themselves to conclude browsers cannot pose CSRF risks. [CSRF protection mechanism](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

`InMemoryUserDetailsManager` and BCrypt make the lab self-contained, but do not provide a complete identity lifecycle management system. When changing environment passwords in the example, you must restart to recreate the in-memory accounts.

## 6. Run and Observe From the Caller Side

### 6.1. Starting on a Personal Machine

In the directory containing `pom.xml`, using PowerShell with `JAVA_HOME` pointing to JDK 21:

```powershell
$env:MONITOR_PASSWORD = 'monitor-local-demo-only'
$env:OPS_PASSWORD = 'ops-local-demo-only'
$env:APP_PASSWORD = 'app-local-demo-only'
mvn spring-boot:run
```

The three strings above are public passwords for the local lab only. For real environments, retrieve credentials from a secret management system; never copy these values onto servers or store real credentials in source code.

The application listens on `http://127.0.0.1:8080`. HTTP Basic in this article is only used on the local loopback address. When transmitting credentials over a network, use HTTPS and verify certificates; Basic's Base64 encoding provides no confidentiality.

### 6.2. Checking Response Codes

Open a second PowerShell terminal. Use `curl.exe` to avoid confusion with the `curl` alias in some PowerShell versions. The commands below print HTTP status codes, not the full response bodies:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/prometheus
curl.exe -s -o NUL -w "%{http_code}\n" -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}\n" -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}\n" -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/prometheus
curl.exe -s -o NUL -w "%{http_code}\n" -u app:app-local-demo-only http://127.0.0.1:8080/api/ping
curl.exe -s -o NUL -w "%{http_code}\n" -u app:app-local-demo-only http://127.0.0.1:8080/actuator/health
```

Corresponding output when the application has started normally:

```text
401
200
403
200
403
200
403
```

The commands include demo passwords for reproducibility. When handling real credentials, avoid putting them into shell history or process argument lists; you can let `curl.exe -u username` prompt interactively for the password.

### 6.3. Checking Visible Data

```powershell
curl.exe -s -u monitor:monitor-local-demo-only http://127.0.0.1:8080/actuator/health
curl.exe -s -u ops:ops-local-demo-only http://127.0.0.1:8080/actuator/health
```

When health is UP, the response for `monitor` is:

```json
{"status":"UP"}
```

The response for `ops` additionally includes `components` and the details provided by health indicators. Do not hardcode this entire JSON: component names, disk space, paths, and numbers depend on the environment.

If a component transitions to DOWN, the aggregate status and health HTTP status code may change; that is a health check result, not automatically an authentication error.

Distinguish when diagnosing:

| Symptom | What to check |
| --- | --- |
| 401 | Missing or invalid credentials under the example's Basic policy |
| 403 on GET | Authenticated but missing the right permission |
| 403 on POST | Could be CSRF or authorization; must separate the two causes |
| Cannot connect | Process, bind address, port, firewall, network route, or TLS |
| Endpoint unusable despite permission | Library dependencies, enabled state, exposure channel, path, and endpoint creation conditions |
| Health reports DOWN/503 | Component status and health status mapping policy |

Do not infer “a disabled endpoint always returns 404”. In the example, an authenticated account calling `/actuator/env` hits the fallback chain and is blocked by `denyAll()` before reaching HTTP handlers. So a 403 response is still consistent with the design.


## 7. Verifying the Policy with Automated Tests

Place the following file at `src/test/java/com/example/leastprivilege/AccessPolicyTest.java`.

The tests go through Spring Security using HTTP Basic, rather than just attaching a mock username to the request. `@AutoConfigureObservability` enables the observability infrastructure needed in the test environment so the Prometheus endpoint can be created.

The test suite deliberately enables `info` **only in the test context**, verifies the endpoint actually exists, and then checks that it is still denied. That ensures results cannot “pass” merely because the endpoint was never created.

```java
package com.example.leastprivilege;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
        "demo.monitor-password=monitor-test-password",
        "demo.ops-password=ops-test-password",
        "demo.app-password=app-test-password",
        "management.endpoint.info.enabled=true",
        "management.endpoints.web.exposure.include=health,prometheus,metrics,loggers,info"
})
@AutoConfigureMockMvc
@AutoConfigureObservability
class AccessPolicyTest {
    @Autowired MockMvc mvc;
    @Autowired WebEndpointsSupplier endpoints;

    @Test
    void healthDetailsDependOnRole() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.components").exists());
    }

    @Test
    void prometheusIsReservedForMonitor() throws Exception {
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isOk());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/actuator/prometheus")
                        .with(httpBasic("app", "app-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void diagnosticsAreReservedForOps() throws Exception {
        for (String path : new String[]{"/actuator/metrics", "/actuator/loggers"}) {
            mvc.perform(get(path)
                            .with(httpBasic("ops", "ops-test-password")))
                    .andExpect(status().isOk());
            mvc.perform(get(path)
                            .with(httpBasic("monitor", "monitor-test-password")))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void loggerWriteIsDeniedEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/actuator/loggers/ROOT")
                        .with(httpBasic("ops", "ops-test-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"configuredLevel\":\"DEBUG\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void applicationAuthorityIsSeparate() throws Exception {
        mvc.perform(get("/api/ping")
                        .with(httpBasic("app", "app-test-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
        mvc.perform(get("/api/ping")
                        .with(httpBasic("monitor", "monitor-test-password")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/ping")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void newlyExposedEndpointStillHasNoPermission() throws Exception {
        assertThat(endpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .contains("info");
        mvc.perform(get("/actuator/info")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCredentialsAndUnexposedPathAreDenied() throws Exception {
        mvc.perform(get("/actuator/health")
                        .with(httpBasic("monitor", "wrong-password")))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/actuator/env")
                        .with(httpBasic("ops", "ops-test-password")))
                .andExpect(status().isForbidden());
    }
}
```

Run in the directory containing `pom.xml`:

```powershell
mvn test
```

The test provides its own passwords via test properties, so this command does not need the three environment variables from the application run session. These are dummy credentials dedicated to testing.

Output to observe on success:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Maven also prints startup info and timings; do not treat the entire log as a fixed string. The goal is that the policy behaves properly, not the appearance of a specific log line.

Evidence to read from the test suite:

- Unauthenticated callers cannot read health.
- Monitoring and operations see health at different detail levels.
- Monitoring can read Prometheus but cannot read diagnostics.
- Operations can read diagnostics but does not automatically have Prometheus access.
- A POST changing log levels is still denied even with a valid CSRF token.
- Application permissions are not inferred from operations or monitoring permissions.
- Adding an endpoint to exposure does not automatically grant access to existing accounts.

This is an in-application test using MockMvc. It does not prove ingress configuration, firewalls, TLS, or external identity mappers are correct. Those boundaries must be verified in the corresponding deployment environment.

## 8. Integrating Monitoring Systems Without Expanding Privileges

### 8.1. Monitoring Scrapers Use a Dedicated Identity

A Prometheus scrape job should use only a metrics-collection identity. Do not take an operator's password and put it into the monitoring server configuration.

The example below is a local Prometheus configuration **when Prometheus and the application share the same host and network namespace**. It illustrates reading a password from a secret file; it is not a file to add to the Maven project:

```yaml
scrape_configs:
  - job_name: actuator-local
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    scheme: http
    basic_auth:
      username: monitor
      password_file: /run/secrets/actuator-monitor-password
    static_configs:
      - targets:
          - 127.0.0.1:8080
```

The `/run/secrets/actuator-monitor-password` file must be provisioned by secret management, containing `monitor`'s exact password. The path must exist in Prometheus's runtime environment and only necessary processes may read it. If Prometheus runs in a container, `127.0.0.1` refers to that container itself; redesign connectivity to fit the environment rather than making the application bind publicly just to fix a connection error.

Prometheus supports `basic_auth.password_file`; do not configure both `password` and `password_file` at the same time. When moving to network connections, configure HTTPS, scrape targets, and an appropriate certificate trust chain. Do not skip certificate verification just to make the connection “work”. [Prometheus HTTP Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#http_config).

### 8.2. Permissions in Tokens or Certificates Must Also Follow the Matrix

In real environments, HTTP Basic can be replaced with the organization's chosen authentication mechanism, such as short-lived tokens or client certificates. Changing the authentication mechanism does not remove authorization requirements.

If using tokens, verify signature, issuer, audience, and expiration; then map claims/scopes to the authorities the application actually checks. A token containing the word “monitoring” in its payload does not automatically satisfy `actuator:prometheus:read`. Scope names and authority names also depend on the configured converter.

If identity is forwarded by a gateway via headers, the application must never trust headers that external callers could set themselves. Restrict trusted sources, strip spoofed headers at the edge, and protect transport between the gateway and the application.

### 8.3. Health Probes Are a Separate Requirement

The example requires authentication for all health calls. A load balancer or probe that sends no credentials will receive 401.

If the platform needs an unauthenticated probe path:

1. Identify the exact probe path and the minimal payload it returns.
2. Place a dedicated rule for that exact path and method before broader rules.
3. Restrict connection sources and rate limits appropriately.
4. Test that this path does not imply permission to view all of health or Actuator.

Do not solve this by permitting all of `/actuator/**`. Nor by adding personal login credentials into every infrastructure probe.

## 9. When Operators Need to Intervene

In the current design, reading loggers and changing log levels are two separate things. If a real incident requires changing log levels, treat that as a policy change:

- Create a separate write authority; do not change the meaning of `actuator:loggers:read`.
- Limit the required resources and methods, such as only approved log-change operations.
- Grant it to the right person, in the right environment, and for the incident window.
- Define a CSRF protection mechanism matching the actual authentication method.
- Record who performed the action, which operation, when, the result, and a correlation ID; avoid logging tokens, passwords, or sensitive data.
- Revoke temporary permissions, restore configuration, and verify afterward.

This article does not automatically add write permissions to the example because the initial requirement is diagnostic read-only. Using Actuator does not automatically create complete approval workflows, permission expiration, and audit logs required by an organization; those parts must be designed separately.

For heap dumps or thread dumps, evaluate returned data, resource consumption, storage location, and retention period before deciding to open access.

## 10. Common Design Mistakes

| Error-prone choice | Consequence | How to adjust |
| --- | --- | --- |
| Exposing all endpoints over HTTP and merely requiring login | Every account may get an overly broad surface if rules are permissive | Explicit endpoint list and deny by default |
| Sharing an account between Prometheus and operations | Leaking one secret impacts multiple workflows and is hard to revoke per party | Separate machine and human identities |
| Giving the monitoring account every GET endpoint | Reads more data than needed and can cause heavy load | Choose endpoints per specific need |
| Checking only `/actuator/loggers` while ignoring HTTP method | Accidentally permits changing log levels | Combine endpoint, method, and authority |
| Securing only the Actuator chain | The rest of the application may be unprotected by any chain | Have a fallback chain covering remaining requests |
| Declaring a custom chain while relying on Boot's old defaults | Effective policy differs from what the author assumes | Explicitly inspect every chain and order |
| Disabling CSRF just because POST returned 403 | Masks the cause and weakens protection for browser flows | Check CSRF and authorization independently |
| Letting health always show details for convenience | Leaks internal structure and details | Control access permission and detail visibility separately |
| Changing ports or disabling discovery and assuming it is secure | Anyone knowing the address can still call directly if other layers allow | Authentication, authorization, and network restrictions |
| Testing only accounts that have access | Misses overly broad permissions | Test a matrix of identities, forbidden operations, and new endpoints |
| Disabling certificate checks when scraping metrics | Fails to verify the server receiving credentials | Configure certificates and trust chain properly |

## 11. Practice Redesigning for a New Requirement

Suppose the on-call team needs to view Prometheus to cross-check charts, without giving all operators this permission permanently.

Answer before modifying code:

1. Can the need be met by existing dashboards, or is calling the source endpoint truly required?
2. Who needs access, in which environment, and for what duration?
3. Should Prometheus read permission be granted to an individual identity for the troubleshooting window?
4. When revoking permission, which test proves original operations permissions still work while the added permission is gone?
5. Is there any data in the monitoring metrics that should not be visible to that group?

A well-grounded option is keeping `ops`'s base permissions unchanged, temporarily granting `actuator:prometheus:read` to the right person upon approval, and revoking it after the incident. You must then test before granting, during the granted window, and after revocation.

After this article, learners should be able to explain every allowed cell in the matrix by a concrete job need, point to the configuration layer enforcing that permission, and provide evidence that out-of-scope permissions were denied.
