# Configure a separate management port and test access permissions

## 1. Practice goal and model

In this exercise, we separate business-traffic HTTP from Spring Boot Actuator management HTTP, then test both aspects:

1. Does the request go to the right port and the right path?
2. Is the caller authenticated and granted the right permissions?

A separate management port puts operational routes on another listener, making routing and network restriction convenient. **Changing the port does not automatically create authentication or authorization.** A sensitive endpoint on another port can still be accessed if network and security allow it.

The lab model uses Spring Boot 3.3.x, Servlet stack, Spring Security 6, and Java 17+:

```text
Spring Boot application, same JVM process
|
+-- 127.0.0.1:8080
|      GET /api/hello
|      Account app, role ROLE_APP
|
+-- 127.0.0.1:9091
       GET /manage/health
       Account operator, role ROLE_OPS

       GET /manage/prometheus
       Account scraper, role ROLE_METRICS
```

Both listeners bind only to loopback so the lab runs locally. In multi-host/container deployments, design appropriate listen addresses and network paths; do not change loopback to all addresses and assume the same access restriction still holds.

### Expected outcomes

- The business account cannot read management data.
- The operations account can read health but cannot read metrics by default.
- The metrics scraper account can only read the Prometheus endpoint.
- Unauthenticated requests are rejected.
- Paths outside the allowlist are rejected.
- Other Actuator endpoints are excluded from the lab's HTTP exposure list.
- Tests verify actual behavior rather than just checking that the YAML file contains the right keys.

This lab uses HTTP Basic over loopback for easy observation. For traffic leaving the local machine, protect credentials with TLS or an equivalently protected transport channel per infrastructure design. HTTP Basic's Base64 is only representation encoding, not security encryption.

## 2. Distinguish four control layers

| Layer | Responsibility | Example in this lab |
| --- | --- | --- |
| Listener and network | Can the request reach the address/port? | Management binds 127.0.0.1:9091 |
| Endpoint and exposure | Which endpoints have exposed HTTP routes? | Only health and prometheus |
| Authentication | Which identity does the request represent? | HTTP Basic, accounts app/operator/scraper |
| Authorization | Which resources may that identity read? | ROLE_OPS reads health, ROLE_METRICS reads Prometheus |

A firewall blocking a port does not replace authorization rules in the application. Conversely, Basic authentication does not turn a public port into a private network.

Having health created and exposed does not mean everyone should be allowed to read it either. In this lab, even health requires authentication; we make that choice intentionally to test permissions clearly.

The configurations below target Spring Boot 3.3.x. Do not copy endpoint properties from another Spring Boot generation into this lab and assume identical semantics.

## 3. Prepare the project and dependencies

Use a Spring Boot 3.3.x project that already has a Gradle wrapper, Boot plugin, and Boot's dependency version management.

Required dependencies section:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}

tasks.named('bootJar') {
    archiveFileName = 'management-port-lab.jar'
}
```

This is a configuration snippet for a project that already has the required plugins, not a complete standalone build file. In a repository with build orchestration, add dependencies using the repository's mechanism; do not create duplicate plugin configuration.

For reproducible results:

- Do not simultaneously add WebFlux to this Servlet lab.
- Do not add other security chains, servlet filters, or reverse proxies without checking their impact.
- Do not override Spring Security/Micrometer versions individually without a verified compatibility reason.
- Ensure ports 8080 and 9091 are free.
- Run with Java 17+ matching the project's target bytecode.

Actuator alone is not enough to publish Prometheus automatically; this lab also requires the Prometheus registry on the runtime classpath.

## 4. Configure the management port and HTTP exposure

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 9091
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,prometheus
  endpoint:
    health:
      show-details: never
      show-components: never
```

Explanation:

- `server.port` is the port for application HTTP traffic.
- `management.server.port` differs from the application port, so Boot creates a separate management web server.
- `management.server.address` restricts the management listener address in this lab.
- `management.endpoints.web.base-path` changes the Actuator prefix from `/actuator` to `/manage`.
- Exposure puts only the two selected endpoints onto HTTP.
- Health does not output details or the component list in this lab.

The two management URLs are:

```text
http://127.0.0.1:9091/manage/health
http://127.0.0.1:9091/manage/prometheus
```

This configuration assumes no extra context/base path and no proxy rewriting paths. When the management server uses a separate port, do not prepend the application server's context path to management URLs automatically.

Exposure neither supplies missing dependencies nor grants access permissions. If another configuration source sets `management.endpoints.web.exposure.exclude`, check it because exclude takes precedence over include.

## 5. Create the application and a business API

### 5.1. Startup class

File `src/main/java/demo/management/ManagementPortLabApplication.java`:

```java
package demo.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementPortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementPortLabApplication.class, args);
    }
}
```

### 5.2. Business controller

File `src/main/java/demo/management/HelloController.java`:

```java
package demo.management;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private final Counter acceptedRequests;

    public HelloController(MeterRegistry registry) {
        acceptedRequests = Counter.builder("lab.api.accepted")
                .description("Requests accepted by the hello handler")
                .register(registry);
    }

    @GetMapping("/api/hello")
    public String hello() {
        acceptedRequests.increment();
        return "hello from application";
    }
}
```

The counter increments only after the request passes security and actually enters the handler. Requests rejected before the handler do not increment this counter.

The name in Micrometer is `lab.api.accepted`; Prometheus output typically has the series `lab_api_accepted_total`. Do not search the exposition output verbatim using the dotted name.

These classes run inside a Spring Boot application with full dependencies. You cannot simply invoke `javac` on the three application files without providing the framework classpath.

## 6. Separate security chains for Actuator and the application

File `src/main/java/demo/management/SecurityConfiguration.java`:

```java
package demo.management;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            Environment environment) {
        var app = User.withUsername("app")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_APP_PASSWORD")))
                .roles("APP")
                .build();

        var operator = User.withUsername("operator")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_OPS_PASSWORD")))
                .roles("OPS")
                .build();

        var scraper = User.withUsername("scraper")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_METRICS_PASSWORD")))
                .roles("METRICS")
                .build();

        return new InMemoryUserDetailsManager(app, operator, scraper);
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to("health"))
                        .hasRole("OPS")
                        .requestMatchers(EndpointRequest.to("prometheus"))
                        .hasRole("METRICS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/hello").hasRole("APP")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }
}
```

### 6.1. Why are ordering and fallback needed?

Spring Security selects the first matching security filter chain by order. Chains do not combine all of their rules for the same request.

- The first chain matches Actuator endpoints using `EndpointRequest`.
- Inside that chain, health and Prometheus have distinct permissions.
- The second chain sets no `securityMatcher`, acting as a fallback for remaining requests.
- The fallback allows only `ROLE_APP` on `/api/hello`; other paths are denied.

If a catch-all chain is placed first, the Actuator chain may never be selected. If only the Actuator chain is defined without ensuring remaining requests have an appropriate chain, unguarded routes may be left exposed.

When the application provides custom security chains, you must design the rules yourself; do not assume Boot's default Actuator security configuration still fills in missing pieces.

### 6.2. Why use EndpointRequest?

`EndpointRequest` resolves Actuator endpoint paths from Boot configuration instead of hardcoding the `/manage` prefix in rules.

It is not a TCP-port matcher. Putting Actuator on a separate management listener is Boot's server configuration responsibility; endpoint access permissions are the security chain's responsibility. Both listener and permissions must be verified.

Do not interpret `securityMatcher(EndpointRequest.toAnyEndpoint())` as “every request on port 9091 enters the first chain.” An unknown path on the management port can still fall through to the fallback chain.

### 6.3. hasRole and authority names

`roles("OPS")` creates the authority `ROLE_OPS`. Therefore, the corresponding rule is `hasRole("OPS")`.

Do not write `hasRole("ROLE_OPS")` by reflexively prepending the prefix. If using `hasAuthority`, match against the full authority string held by the identity.

In this lab, `ROLE_OPS` does not imply `ROLE_METRICS` or `ROLE_APP`. No role hierarchy is declared; operator does not automatically become an all-powerful administrator.

### 6.4. Scope of authentication and CSRF

The application uses HTTP Basic, not form login. Testing with curl will show HTTP authentication challenges rather than having to follow an HTML login page.

All test operations are GET. The configuration does not disable CSRF globally and exposes no state-changing endpoints. When adding POST/DELETE operations or another authentication mechanism, you must design and test corresponding CSRF requirements; do not infer from passing GET calls.

`STATELESS` reflects the choice not to use HTTP sessions to maintain login state in this lab. It is not by itself a sufficient reason to disable CSRF for every client type or authentication scheme.

### 6.5. Passwords are session-only lab data

The three passwords are read from the environment, not hardcoded in source. If a required variable is missing, the application cannot build the user store and will fail to start normally.

An in-memory user store fits a lab exercise; when moving to a real system, choose an identity store, credential revocation/rotation mechanisms, and authorization matching system requirements.

Do not print password variables or Authorization headers into test reports. BCrypt hashing in the user store does not protect passwords in transit over HTTP; those are two separate layers.

## 7. Prepare passwords and start up

Enter three separate passwords for the lab session. The commands below do not echo passwords to the terminal. To avoid HTTP Basic charset differences across tools, use non-empty ASCII passwords for this lab.

### 7.1. Bash

```bash
read -r -s -p "Password for app: " LAB_APP_PASSWORD
printf '\n'
export LAB_APP_PASSWORD

read -r -s -p "Password for operator: " LAB_OPS_PASSWORD
printf '\n'
export LAB_OPS_PASSWORD

read -r -s -p "Password for scraper: " LAB_METRICS_PASSWORD
printf '\n'
export LAB_METRICS_PASSWORD

./gradlew bootJar
java -jar build/libs/management-port-lab.jar
```

### 7.2. PowerShell

```powershell
$labAppSecret = Read-Host "Password for app" -AsSecureString
$env:LAB_APP_PASSWORD = [System.Net.NetworkCredential]::new("", $labAppSecret).Password

$labOpsSecret = Read-Host "Password for operator" -AsSecureString
$env:LAB_OPS_PASSWORD = [System.Net.NetworkCredential]::new("", $labOpsSecret).Password

$labMetricsSecret = Read-Host "Password for scraper" -AsSecureString
$env:LAB_METRICS_PASSWORD = [System.Net.NetworkCredential]::new("", $labMetricsSecret).Password

.\gradlew.bat bootJar
java -jar build/libs/management-port-lab.jar
```

Environment variables are process inputs, not a long-term secret store. Keep them scoped to the lab session, do not capture/print the entire environment, and do not commit values into source.

Read the logs to confirm both web servers started on the expected ports. Having the first web server start is not enough if the management port is occupied and the application fails afterward.

You can cross-check listeners using OS tools. In PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080,9091 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Exact output depends on the host machine. You should see listeners matching `127.0.0.1` and the right process, without copying an assumed PID into a report.

If using a second terminal for HTTP checks, keep the application running. The Java check program in the later section also needs all three environment variables; a newly opened terminal elsewhere may not inherit variables set in the startup terminal.

## 8. Access matrix to verify

With the lab configuration and a healthy application:

| Request | Unauthenticated | app / ROLE_APP | operator / ROLE_OPS | scraper / ROLE_METRICS |
| --- | --- | --- | --- | --- |
| 8080/api/hello | 401 | 200 | 403 | 403 |
| 9091/manage/health | 401 | 403 | 200 | 403 |
| 9091/manage/prometheus | 401 | 403 | 403 | 200 |

Interpretation:

- `401`: no valid identity yet, such as missing or wrong password.
- `403`: authenticated but lacking the required permission, for the GET requests in this lab.
- `200`: passed security and handler returned a successful result.
- Connection error: did not reach the HTTP layer; do not interpret as a role error.
- `503` from health: can indicate an unhealthy status, not a wrong password or wrong role.

A `403` response on state-changing methods can also involve CSRF. Therefore, do not apply the simplified GET matrix interpretation to POST/DELETE requests.

### 8.1. Manual checks with curl

Use single-line syntax for easy portability across shells. On Windows, invoke `curl.exe` if `curl` is a PowerShell alias.

Unauthenticated request:

```bash
curl -i http://127.0.0.1:9091/manage/health
```

Expect `401` and an HTTP Basic challenge header. Do not add `-L` and mask redirects if some other configuration introduces a redirect.

Requests with authorized accounts:

```bash
curl -i --user operator http://127.0.0.1:9091/manage/health
curl -i --user scraper http://127.0.0.1:9091/manage/prometheus
curl -i --user app http://127.0.0.1:8080/api/hello
```

curl prompts for the password when given only a username. No need to put passwords directly in URLs or command arguments.

For a successful API request, the body is:

```text
hello from application
```

The body has no trailing newline added by controller code. Because `-i` is used, the terminal also displays headers; headers and dynamic headers are not fixed lab output.

For health, in a healthy test environment with no custom contributors:

```json
{"status":"UP"}
```

If health reports otherwise, check the resources measured by health contributors before concluding authentication configuration is broken.

Requests with a valid password but wrong role:

```bash
curl -i --user app http://127.0.0.1:9091/manage/health
curl -i --user operator http://127.0.0.1:9091/manage/prometheus
curl -i --user scraper http://127.0.0.1:8080/api/hello
```

Expect `403` for all three. Do not test only one authorized account and conclude all permissions are properly separated.

### 8.2. Test wrong password

Re-run a request with a valid username and enter a password different from the configured one:

```bash
curl -i --user operator http://127.0.0.1:9091/manage/health
```

Expect `401`, not `403`. This case proves the authentication step is distinct from the role check.

Do not record wrong or right passwords in logs/reports; record only the test label and received status.

### 8.3. Test unlisted paths

```bash
curl -i --user operator http://127.0.0.1:9091/manage/env
```

With the lab's security configuration, this request is denied by the fallback chain and returns `403`. The `env` endpoint is also absent from exposure include.

These two pieces of evidence serve different roles: a `403` proves the request was blocked; it does not by itself prove there is no handler behind it. Exposed endpoints must be cross-checked against effective configuration and application mappings when needed.

The `/manage` discovery path is not granted separate permission in the example. Thus, operator being unable to open the root links page does not contradict being able to read `/manage/health`. Do not treat the discovery page as a prerequisite for health or metrics to work.

## 9. Automate the matrix with Java 17

The program below sends only GET requests to the two local listeners. It needs no Spring dependencies, prints no passwords, and follows no redirects. It verifies status codes along with a body marker for allowed requests.

File `AccessMatrixCheck.java`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;

public class AccessMatrixCheck {

    record Check(
            String name,
            String url,
            String username,
            String password,
            int expectedStatus,
            String bodyFragment) {
    }

    public static void main(String[] args) throws Exception {
        String appPassword = required("LAB_APP_PASSWORD");
        String opsPassword = required("LAB_OPS_PASSWORD");
        String metricsPassword = required("LAB_METRICS_PASSWORD");

        String appUrl = "http://127.0.0.1:8080/api/hello";
        String healthUrl = "http://127.0.0.1:9091/manage/health";
        String metricsUrl = "http://127.0.0.1:9091/manage/prometheus";

        List<Check> checks = List.of(
                new Check("app-anonymous", appUrl,
                        null, null, 401, null),
                new Check("app-app", appUrl,
                        "app", appPassword, 200, "hello from application"),
                new Check("app-operator", appUrl,
                        "operator", opsPassword, 403, null),
                new Check("app-scraper", appUrl,
                        "scraper", metricsPassword, 403, null),

                new Check("health-anonymous", healthUrl,
                        null, null, 401, null),
                new Check("health-app", healthUrl,
                        "app", appPassword, 403, null),
                new Check("health-operator", healthUrl,
                        "operator", opsPassword, 200, "\"UP\""),
                new Check("health-scraper", healthUrl,
                        "scraper", metricsPassword, 403, null),

                new Check("metrics-anonymous", metricsUrl,
                        null, null, 401, null),
                new Check("metrics-app", metricsUrl,
                        "app", appPassword, 403, null),
                new Check("metrics-operator", metricsUrl,
                        "operator", opsPassword, 403, null),
                new Check("metrics-scraper", metricsUrl,
                        "scraper", metricsPassword, 200,
                        "lab_api_accepted_total"),

                new Check("env-operator",
                        "http://127.0.0.1:9091/manage/env",
                        "operator", opsPassword, 403, null)
        );

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        boolean failed = false;

        for (Check check : checks) {
            try {
                HttpRequest.Builder request = HttpRequest.newBuilder()
                        .uri(URI.create(check.url()))
                        .timeout(Duration.ofSeconds(5))
                        .GET();

                if (check.username() != null) {
                    String credentials = check.username() + ":"
                            + check.password();
                    String basic = Base64.getEncoder().encodeToString(
                            credentials.getBytes(StandardCharsets.UTF_8));
                    request.header("Authorization", "Basic " + basic);
                }

                HttpResponse<String> response = client.send(
                        request.build(),
                        HttpResponse.BodyHandlers.ofString());

                boolean ok = response.statusCode() == check.expectedStatus()
                        && (check.bodyFragment() == null
                        || response.body().contains(check.bodyFragment()));

                System.out.printf("%s %s expected=%d actual=%d%n",
                        ok ? "PASS" : "FAIL",
                        check.name(),
                        check.expectedStatus(),
                        response.statusCode());

                if (!ok) {
                    failed = true;
                }
            } catch (Exception exception) {
                failed = true;
                System.out.println("FAIL " + check.name()
                        + " transport="
                        + exception.getClass().getSimpleName());
            }
        }

        System.out.println("RESULT=" + (failed ? "FAIL" : "PASS"));
        if (failed) {
            System.exit(1);
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required environment variable: " + name);
        }
        return value;
    }
}
```

Compile and run from a terminal where the three environment variables are set:

```bash
javac --release 17 AccessMatrixCheck.java
java AccessMatrixCheck
```

These `javac` and `java` commands also work in PowerShell if the JDK is on PATH.

With the lab configuration, matching passwords, healthy application, and no extra proxy/filter layers, stdout is:

```text
PASS app-anonymous expected=401 actual=401
PASS app-app expected=200 actual=200
PASS app-operator expected=403 actual=403
PASS app-scraper expected=403 actual=403
PASS health-anonymous expected=401 actual=401
PASS health-app expected=403 actual=403
PASS health-operator expected=200 actual=200
PASS health-scraper expected=403 actual=403
PASS metrics-anonymous expected=401 actual=401
PASS metrics-app expected=403 actual=403
PASS metrics-operator expected=403 actual=403
PASS metrics-scraper expected=200 actual=200
PASS env-operator expected=403 actual=403
RESULT=PASS
```

The program does not print full bodies, so it keeps metric data or error pages out of test stdout. When status matches but the body lacks the expected marker, the corresponding line still reports FAIL even though expected and actual match.

If a request errors or mismatches expectations, the program continues checking remaining cases and then exits with code 1. On success, exit code is 0.

This is an external HTTP check against the application. It verifies the matrix within the stated scope, and does not replace TLS, discovery, firewall, or all-HTTP-method testing for a real deployment.

## 10. Verify separate ports and network boundaries

### 10.1. Cross-port checks

Also test:

```bash
curl -i --user operator http://127.0.0.1:8080/manage/health
curl -i --user app http://127.0.0.1:9091/api/hello
```

These paths must not return successful resource payloads on the wrong listener. In an application with security filters, you may receive `403` before handler lookup or `404` after passing security with no mapping. Do not insist that every wrong-port test must return strictly `404`.

If you receive `200` with the resource's body on the wrong port, re-check port configuration, mappings, controllers, or proxies. Looking only at port numbers in a config file does not prove real separation.

A wrong-port path blocked by security is not enough by itself to prove no mapping exists behind it. Combine this result with actual listeners, startup logs, and effective management configuration.

### 10.2. Separate network testing from authorization testing

With listeners bound only to `127.0.0.1`, direct access from another machine via the host's LAN address is not served by that loopback listener. Check the right network namespace: loopback inside a container is not the host's loopback.

When deploying with a dedicated management network:

- Choose the appropriate interface address.
- Allow connections only from required monitoring/operations sources.
- Verify allowed requests traverse the expected network path.
- Test unauthorized sources within infrastructure testing scope.
- Still enforce identity and permissions at the application layer.

If a source is blocked by a firewall, it has not tested application role rules yet. If an internal test receives `403`, it has not proven the external firewall is right yet.

### 10.3. Containers, proxies, and health probes

If Prometheus runs in another container, Prometheus's `127.0.0.1:9091` does not point to the Spring Boot container. The local lab uses loopback to minimize scope; moving to containers requires explicitly redesigning listeners, networking, and target names.

Do not publish the management port to the host or internet by habit just because it is a separate port. If accessed via a proxy, also check direct backend routes so rules you think the proxy enforces cannot be bypassed.

A successful health check on the management listener does not by itself prove the application listener is accepting business requests normally. When designing readiness/liveness for deployment, choose probes and check paths suited to the application's actual serving capability.

At the same time, orchestrator probes must be compatible with the chosen authentication policy. This lab requires authentication on health; if the orchestrator cannot send the required credentials, do not conclude the health endpoint “stopped working on its own.”

## 11. Diagnose unexpected results

| Symptom | Check first |
| --- | --- |
| Fails to start, missing property | Are the three password variables in the Java process's environment? |
| Port already in use | Which port is occupied, by which process? Was the previous run stopped? |
| Connection refused on 9091 | Did the management server start, on the right address/port and network namespace? |
| 404 on /actuator/health | The lab changed base path to /manage; are you calling the right port? |
| Valid account still gets 401 | Do the client password values match the currently running app session? |
| App account can read health | Were chain order, matchers, permitAll rules, or effective Security config changed? |
| Operator gets 403 on health | Is the authority exactly ROLE_OPS? Which chain is the request entering? |
| Operator cannot read Prometheus | Expected in this lab: operator does not have ROLE_METRICS |
| Health 503 with valid auth | Read health status and check resources; do not change roles to fix DOWN |
| Scraper gets 404 on Prometheus | Is the registry on the runtime classpath, and is the endpoint enabled and exposed? |
| Prometheus 200 but missing counter | Did you use the right registry, exported metric name, and instance? |
| Returns HTML or login redirect | Is form login, a proxy, or another security chain interfering? |
| Anonymous can read management data | Is there an unintended permit rule, another listener/proxy, or a different running artifact? |

When Spring Security diagnostic logs are needed, enable them only for the test session and inspect which chain and matcher were selected. Do not log Authorization headers or passwords. After any change, restart if needed and re-run the entire matrix, because changing one shared rule can affect multiple routes.

Do not fix a `401` by opening all endpoints, nor fix a connection error by granting extra roles. Each layer requires corresponding evidence and the right fix.

## 12. Acceptance criteria and session cleanup

The lab is complete when:

1. Both listeners start on the chosen addresses and ports.
2. The business API works with the app account.
3. Health is readable only by operator in the designed matrix.
4. Prometheus is readable only by scraper in the designed matrix.
5. Unauthenticated requests and unauthorized requests are rejected as expected.
6. Wrong-password test distinguishes authentication failures from authorization failures.
7. Unlisted paths are rejected and HTTP exposure remains limited to the intended endpoints.
8. Cross-port requests do not return resource payloads on the wrong listener.
9. The check program prints RESULT=PASS against the exact deployed app and configuration.
10. Local-lab limitations are documented when transitioning to other networks, TLS, or identity systems.

At the end of the session, stop the test process and clear the password variables from the terminal when no longer needed.

Bash:

```bash
unset LAB_APP_PASSWORD LAB_OPS_PASSWORD LAB_METRICS_PASSWORD
```

PowerShell:

```powershell
Remove-Item Env:LAB_APP_PASSWORD
Remove-Item Env:LAB_OPS_PASSWORD
Remove-Item Env:LAB_METRICS_PASSWORD
```

Clearing variables in the terminal does not alter the environment of a Java process started earlier; therefore stop the test process separately.

What must be proven throughout the exercise is that **the management port is properly separated, exposed endpoints are bounded, and each identity holds only its designed permissions**. The allow/deny matrix is the behavioral evidence backing that configuration.
