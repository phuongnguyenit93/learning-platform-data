# Verifying Anonymous, Unauthorized, and Authorized Access Including the Management Port

## 1. Goal: Proving the Policy With Concrete Requests

A security configuration can look right yet still protect the wrong resource, wrong path, or be tested only on the application port. When Actuator runs on a separate management port, tests must send requests to **the actual management server**, rather than loading a single filter chain and assuming every port is secure.

Each verification check must specify:

- Target: protocol, address, port, and path.
- HTTP method.
- Identity: unauthenticated, validly logged in but lacking permission, or holding sufficient permission.
- Expected outcome: status code, required headers, and a marker identifying the right resource.

This article builds a Java 21, Spring Boot 3.3.13, Spring MVC/Servlet project. It has application port 8080 and Actuator port 9090. The test suite uses two real OS-assigned ports, sends HTTP over loopback, and verifies JSON content as well.

HTTP tests on the machine running the application prove the behavior of both servers and their security configuration there. Access from the Internet, from another namespace, through a reverse proxy, or over TLS still needs testing in the corresponding deployment environment.

## 2. Distinguishing Three Cases by Identity and Permission

### 2.1. Anonymous Access

The caller sends no credentials, such as no Authorization header and no logged-in session.

For endpoints requiring authentication via HTTP Basic, this sample returns **401 Unauthorized**, with a `WWW-Authenticate` header starting with `Basic`. That result indicates the request does not yet carry an accepted identity.

### 2.2. Wrong Permission

The caller uses a real account and the right password, yet lacks the authority or role required by the endpoint. In the sample, the result is **403 Forbidden**.

Do not use a wrong password to test the “wrong permission” case. A wrong password causes authentication to fail, so it does not prove authorization rules were applied to a valid identity.

### 2.3. Right Permission

The account is authenticated and holds the required permission. For the two selected GET operations in this article, the expected outcome is **200 OK** and the JSON content of the exact endpoint.

A bare 200 is not enough. A proxy could return an HTML page, a client could follow a redirect, or a test author could call the wrong API and still get 200. Therefore, also verify content type and a distinctive value in the response.

| Scenario | Username/password | Required permission | Outcome in sample |
| --- | --- | --- | --- |
| Anonymous | Not sent | None yet | 401 |
| Wrong password | Right username, wrong password | Not authenticated | 401 |
| Wrong permission | Right | Missing | 403 |
| Right permission | Right | Sufficient | 200 with expected content |

These codes are expectations for the selected endpoints and Basic mechanism. Do not apply them mechanically to every operation: POST can be rejected by CSRF; health can return 503 due to unhealthy status; misconfiguration or proxies can also produce different responses.

## 3. Two Ports Are Two HTTP Targets to Test Independently

Diagram of the hands-on lab:

```text
HTTP client
  |
  +-- http://127.0.0.1:8080/api/report
  |       Application server
  |       Requires REPORT_READER role
  |
  +-- http://127.0.0.1:9090/actuator/info
          Management server
          Requires ACTUATOR role

Intentional exception:
http://127.0.0.1:9090/actuator/health
    Permits anonymous access, returns aggregate status only
```

Separating ports helps organize access paths but does not automatically create authentication or authorization. Port 9090 still needs security policies, listen address configuration, and proper network controls.

Sample users:

| User | Role | Purpose |
| --- | --- | --- |
| reporter | REPORT_READER | Read reports on the application port |
| operator | ACTUATOR | Read Actuator info on the management port |

Main matrix:

| GET Target | Anonymous | reporter, right password | operator, right password |
| --- | --- | --- | --- |
| 8080 — `/api/report` | 401 | 200 | 403 |
| 9090 — `/actuator/info` | 401 | 403 | 200 |
| 9090 — `/actuator/health` | 200 | 200 | 200 |

The health row is a designed exception, not proof that Actuator is completely open. An account does not automatically receive permissions in both groups just by logging in successfully in one group.

In Boot 3.3, a separate management port is configured via `management.server.port`. See [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 4. Complete Hands-On Project

### 4.1. File Structure

```text
management-port-verification/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── PortLabApplication.java
    │   │   └── PortSecurity.java
    │   └── resources/application.yml
    └── test/java/example/
        └── PortAccessTest.java
```

### 4.2. pom.xml

Use JDK 21 and Maven 3.6.3+. Spring versions are managed by Spring Boot 3.3.13.

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
    <groupId>example</groupId>
    <artifactId>management-port-verification</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 4.3. src/main/resources/application.yml

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: true

info:
  app:
    name: management-port-verification

lab:
  reporter-password: ${REPORTER_PASSWORD}
  operator-password: ${OPERATOR_PASSWORD}
```

Notable choices:

- 8080 and 9090 are fixed ports for manual runs. During tests, they are replaced by random ports.
- Both servers listen only on loopback for personal-machine practice. Do not use this address for a collector or caller on another machine/Pod and expect them to reach it.
- Only health and info are exposed over HTTP.
- `management.info.env.enabled` allows `info.*` data to appear in the info response. The `info.app.name` value is the marker used to confirm the right endpoint.
- Health returns no component structure or internal details.
- Both passwords come from environment variables; there are no default passwords in application config.

Exposure configuration only decides which endpoints are published over HTTP. It does not replace access permissions. Data placed under `info.*` must also be curated before exposing.

### 4.4. src/main/java/example/PortLabApplication.java

```java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PortLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortLabApplication.class, args);
    }

    @RestController
    static class ReportController {
        @GetMapping("/api/report")
        Map<String, String> report() {
            return Map.of("result", "report-ok");
        }
    }
}
```

The report API returns a fixed value to verify that the request passed security and reached the right controller. It is a small test for separation between the application and Actuator.

### 4.5. src/main/java/example/PortSecurity.java

```java
package example;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class PortSecurity {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(rules -> rules
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .anyRequest().hasRole("ACTUATOR"));
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(rules -> rules
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/report")
                        .hasRole("REPORT_READER")
                .anyRequest().authenticated());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${lab.reporter-password}") String reporterPassword,
            @Value("${lab.operator-password}") String operatorPassword) {
        var reporter = User.withUsername("reporter")
                .password(encoder.encode(reporterPassword))
                .roles("REPORT_READER")
                .build();
        var operator = User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .roles("ACTUATOR")
                .build();
        return new InMemoryUserDetailsManager(reporter, operator);
    }
}
```

How to read the two chains:

1. The Actuator chain is evaluated first, selecting endpoints via Servlet `EndpointRequest`. Health is intentionally public; remaining Actuator endpoints require the ACTUATOR role.
2. The second chain covers all remaining requests. GET to the report API requires REPORT_READER; other paths require authentication.
3. Once a chain matches, the request does not continue into a later chain to find a more permissive rule. See [SecurityFilterChain architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html#servlet-securityfilterchain).
4. `roles("ACTUATOR")` creates authority `ROLE_ACTUATOR`, corresponding to `hasRole("ACTUATOR")`. Similarly for REPORT_READER.
5. Both chains enable Basic and do not store SecurityContext in HTTP sessions. Each verification call sends its own credentials.
6. CSRF is kept intact. The main checks use GET; there is no need to disable CSRF to prove these three access scenarios.

The rule for `DispatcherType.ERROR` allows internal error handling to return the original error response. It does not grant `permitAll()` to direct requests targeting the `/error` URL. This keeps 404 tests from having their initial result masked by a security check during error dispatch.

The final `authenticated()` rule is a choice of the lab project, letting a logged-in user reach handler lookup for non-existent paths. When integrating into a real system, provide a complete policy for real APIs rather than blindly using this fallback rule for every application.

Types in this article belong to Servlet: `HttpSecurity`, `SecurityFilterChain`, and `EndpointRequest` in the `.servlet` branch. For WebFlux you must use `ServerHttpSecurity`, `SecurityWebFilterChain`, and Reactive matchers; do not mix types across the two API stacks.

## 5. Manual Verification With curl

### 5.1. Run the Application

In the terminal containing the project, set passwords dedicated to the lab.

Bash:

```bash
export REPORTER_PASSWORD='lab-reporter-pass'
export OPERATOR_PASSWORD='lab-operator-pass'
mvn spring-boot:run
```

PowerShell:

```powershell
$env:REPORTER_PASSWORD = 'lab-reporter-pass'
$env:OPERATOR_PASSWORD = 'lab-operator-pass'
mvn spring-boot:run
```

These two passwords are public demo data. Never replace them with real secrets in a command saved to shell history or committed to a repository.

You can package and run with Java:

```bash
mvn package
java -jar target/management-port-verification-1.0.0.jar
```

Keep the environment variables in the terminal running the JAR. Run only one application instance to avoid port 8080 or 9090 conflicts. The project requires Spring dependencies, so use Maven to compile and build the classpath; running standalone `javac` on one file will not download libraries.

Wait for both servers to finish starting. Seeing only one port active does not satisfy conditions for testing the two-port matrix.

### 5.2. Six Core Requests

Open a second terminal. Commands below use Bash. In PowerShell use `curl.exe` and replace `/dev/null` with `NUL`.

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9090/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:9090/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:9090/actuator/info
```

Results in order:

```text
401
403
200
401
403
200
```

Do not use `-L` in the initial verification pass because you need to see the raw redirect response if one occurs. Curl by default does not treat 4xx/5xx HTTP codes as process errors; a script must check expected HTTP codes rather than relying only on curl's exit code.

If the connection is refused or times out, you may see `000` and an error message. That is a connection failure, not a successful or failed authentication response.

### 5.3. Inspecting 401 Headers and 200 Bodies

Unauthenticated request:

```bash
curl -i http://127.0.0.1:9090/actuator/info
```

Check status code 401 and the `WWW-Authenticate` header announcing Basic. Do not match every header verbatim because Date, connection details, or header order can vary.

Two authorized requests:

```bash
curl -sS -u reporter:lab-reporter-pass http://127.0.0.1:8080/api/report
curl -sS -u operator:lab-operator-pass http://127.0.0.1:9090/actuator/info
```

Body of the report request:

```json
{"result":"report-ok"}
```

Body of the info request in the sample configuration:

```json
{"app":{"name":"management-port-verification"}}
```

These are HTTP response bodies; curl does not insert newlines between the two commands. In automated tests, parse JSON and check required values instead of relying on line breaks or whitespace.

### 5.4. Wrong Passwords and Wrong Ports

Use the right username with a wrong password:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:wrong-password http://127.0.0.1:8080/api/report
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:wrong-password http://127.0.0.1:9090/actuator/info
```

Both return 401. This result supplements authentication testing; it does not replace the two wrong-permission tests using valid passwords.

To check whether endpoints are served on the wrong port, use valid identities so authentication failure does not mask handler lookup:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -u operator:lab-operator-pass http://127.0.0.1:8080/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" -u reporter:lab-reporter-pass http://127.0.0.1:9090/api/report
```

In the lab configuration, both return 404. The first request verifies info is not served on the application port; the second verifies the report controller is not served on the management port.

An anonymous request to a wrong URL can be blocked with 401 before handler lookup. Thus, merely seeing 401 on port 8080 does not prove Actuator endpoints live on that port.

## 6. Why Must the Test Suite Use Real Servers?

`@SpringBootTest` uses a MOCK environment by default. A MockMvc test can verify authorization rules well, yet does not prove the management server is listening on a separate port or that clients actually sent requests to that port.

This article requires:

- `webEnvironment = RANDOM_PORT` to start the application server.
- `management.server.port=0` to request a random management port.
- `@LocalServerPort` to obtain the actual assigned application port.
- `@LocalManagementPort` to obtain the actual assigned management port.
- An assertion that both port numbers are positive and distinct.

The value 0 tells the OS to allocate a port, not a port for clients to connect to. Do not construct URLs from `management.server.port` while the configured value is still 0.

TestRestTemplate provided by Boot can use relative URLs bound to the application port. Calling `"/actuator/info"` on that client does not automatically route to the management port. The test suite below always builds absolute URLs from the resolved ports.

Starting real servers and supporting a separate management port are described in [Testing Spring Boot Applications 3.3](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

## 7. src/test/java/example/PortAccessTest.java

This is the complete test file. It does not use `@WithMockUser` or inject a pre-built Authentication object; each request sends Basic credentials to the real servers. Test passwords are supplied via properties with higher precedence than YAML, so the environment variables for manual runs are unnecessary.

```java
package example;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.util.stream.Stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "lab.reporter-password=test-reporter-pass",
                "lab.operator-password=test-operator-pass"
        })
class PortAccessTest {
    @LocalServerPort
    int applicationPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    ObjectMapper json;

    static Stream<Arguments> accessCases() {
        return Stream.of(
                Arguments.of("app anonymous", false, null, null,
                        HttpStatus.UNAUTHORIZED),
                Arguments.of("app wrong role", false, "operator", "test-operator-pass",
                        HttpStatus.FORBIDDEN),
                Arguments.of("app correct role", false, "reporter", "test-reporter-pass",
                        HttpStatus.OK),
                Arguments.of("management anonymous", true, null, null,
                        HttpStatus.UNAUTHORIZED),
                Arguments.of("management wrong role", true, "reporter", "test-reporter-pass",
                        HttpStatus.FORBIDDEN),
                Arguments.of("management correct role", true, "operator", "test-operator-pass",
                        HttpStatus.OK)
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("accessCases")
    void verifiesAccessMatrix(String label, boolean management,
            String username, String password, HttpStatus expected) throws Exception {
        int port = management ? managementPort : applicationPort;
        String path = management ? "/actuator/info" : "/api/report";
        ResponseEntity<String> response = get(port, path, username, password);

        assertThat(response.getStatusCode()).as(label).isEqualTo(expected);
        assertThat(response.getHeaders().getLocation()).isNull();
        if (expected == HttpStatus.UNAUTHORIZED) {
            assertThat(response.getHeaders().getFirst(HttpHeaders.WWW_AUTHENTICATE))
                    .startsWith("Basic ");
        }
        if (expected == HttpStatus.OK) {
            assertThat(response.getHeaders().getContentType())
                    .isNotNull()
                    .satisfies(type ->
                            assertThat(type.isCompatibleWith(MediaType.APPLICATION_JSON)).isTrue());
            var body = json.readTree(response.getBody());
            if (management) {
                assertThat(body.path("app").path("name").asText())
                        .isEqualTo("management-port-verification");
            }
            else {
                assertThat(body.path("result").asText()).isEqualTo("report-ok");
            }
        }
    }

    static Stream<Arguments> badPasswords() {
        return Stream.of(
                Arguments.of(false, "/api/report", "reporter"),
                Arguments.of(true, "/actuator/info", "operator")
        );
    }

    @ParameterizedTest
    @MethodSource("badPasswords")
    void rejectsWrongPassword(boolean management, String path, String username) {
        int port = management ? managementPort : applicationPort;
        var response = get(port, path, username, "wrong-password");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void usesTwoDistinctActualPorts() {
        assertThat(applicationPort).isPositive();
        assertThat(managementPort).isPositive().isNotEqualTo(applicationPort);
    }

    @Test
    void managementHealthIsPublicAndMinimal() throws Exception {
        var response = get(managementPort, "/actuator/health", null, null);
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        var body = json.readTree(response.getBody());
        assertThat(body.path("status").asText()).isEqualTo("UP");
        assertThat(body.has("components")).isFalse();
        assertThat(body.has("details")).isFalse();
    }

    @Test
    void actuatorInfoIsNotServedOnApplicationPort() {
        var response = get(applicationPort, "/actuator/info",
                "operator", "test-operator-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void businessControllerIsNotServedOnManagementPort() {
        var response = get(managementPort, "/api/report",
                "reporter", "test-reporter-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void discoveryLinksAlsoRequireActuatorRole() {
        var forbidden = get(managementPort, "/actuator",
                "reporter", "test-reporter-pass");
        var allowed = get(managementPort, "/actuator",
                "operator", "test-operator-pass");
        assertThat(forbidden.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(allowed.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void unexposedEndpointIsNotMistakenForAnAuthorizationFailure() {
        var response = get(managementPort, "/actuator/env",
                "operator", "test-operator-pass");
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    private ResponseEntity<String> get(int port, String path,
            String username, String password) {
        var factory = new SimpleClientHttpRequestFactory() {
            @Override
            protected void prepareConnection(HttpURLConnection connection,
                    String method) throws IOException {
                super.prepareConnection(connection, method);
                connection.setInstanceFollowRedirects(false);
            }
        };
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(5000);
        var client = new TestRestTemplate(new RestTemplateBuilder()
                .requestFactory(() -> factory));

        var headers = new HttpHeaders();
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));
        if (username != null) {
            headers.setBasicAuth(username, password, StandardCharsets.UTF_8);
        }
        String url = "http://127.0.0.1:" + port + path;
        return client.exchange(url, HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);
    }
}
```

## 8. Reading the Test Suite by What It Proves

### 8.1. Six-Case Matrix

`accessCases()` produces six executions of the same method:

1. Application API, anonymous.
2. Application API, valid operator lacking REPORT_READER.
3. Application API, authorized reporter.
4. Actuator on management port, anonymous.
5. Actuator on management port, valid reporter lacking ACTUATOR.
6. Actuator on management port, authorized operator.

For 401, the test checks the Basic challenge. For 200, the test checks JSON-compatible Content-Type and then reads a distinctive value. It also asserts no Location header is present to avoid overlooking an unexpected redirect.

Using the same path, same method, and varying only identity within each group isolates that the difference comes from access permissions rather than accidentally testing two different resources.

### 8.2. Two Wrong-Password Cases

The two executions of `rejectsWrongPassword` check authentication on both ports. They stay separate from wrong permission because they use an invalid password.

If a test uses a nonexistent username and expects 403, that test confuses its preconditions. It needs an authenticated account that specifically lacks the required permission.

### 8.3. Checking That the Response Belongs to the Right Resource

For the API, JSON must contain `result=report-ok`. For Actuator info, JSON must contain `app.name=management-port-verification`.

This catches many bugs that a status-200-only check misses: wrong port, wrong URL, an upstream route returning a default page, or response content not belonging to the verified resource.

Do not assert unnecessary fields such as exact response times, Date headers, or JSON property ordering. Those details can change while the policy remains valid.

### 8.4. Port Separation and Exceptions

Two cross-port checks use valid identities and expect 404:

- Actuator info does not appear on the application port.
- Business controller does not appear on the management port.

Health on the management port is tested separately because it is intentionally public. The test does not treat every 200 for anonymous callers as a vulnerability; compare against that endpoint's policy.

The discovery links endpoint `/actuator` is also tested: reporter is denied, operator can read it. Testing the links endpoint separately avoids protecting only sub-URLs while overlooking the base path.

The `env` test uses operator and expects 404 because that endpoint is unexposed in the sample. It prevents misinterpreting “nonexistent/unexposed” as “missing permission”.

### 8.5. Client Does Not Mask Outcomes

The `get` helper creates a client and headers per request. When username is null, it attaches no Basic auth; identities never share headers from earlier calls.

`SimpleClientHttpRequestFactory` sets timeouts and disables automatic redirect following. A 302 needs to be observed on this verification pass, rather than turning into a 200 from a login page after another request.

TestRestTemplate preserves 4xx/5xx responses so status codes can be asserted. That does not mean a connection error turns into a ResponseEntity with status 401. Connection errors must fail the test and be investigated separately. See [TestRestTemplate 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html).

## 9. Running the Test Suite and Evaluating Results

In the project directory:

```bash
mvn clean test
```

The test suite generates **14 test executions**:

| Group | Executions |
| --- | --- |
| Access matrix across both ports | 6 |
| Wrong password across both ports | 2 |
| Two ports actually distinct | 1 |
| Public and minimal health | 1 |
| Two cross-port tests | 2 |
| Links endpoint read permission | 1 |
| Unexposed endpoint | 1 |
| Total | 14 |

Success criteria: 14 executed, zero failures, errors, or skipped. Port numbers and run durations vary.

If tests only cover the three cases on the application port, they do not meet the goal of verifying the management port. If they only use `@WithMockUser` in a simulated environment, they do not test passwords, Basic auth, or real connections to the management port.

These tests only read data and mutate no business state. When extending to write operations in real HTTP tests, remember that transactions on the server thread are not automatically rolled back just because the test method has `@Transactional`.

## 10. Diagnosing by Failure Layer

| Observation | What to verify |
| --- | --- |
| Connection refused | Has that server started; right address/port; any port conflict |
| Timeout | Network path, bind address, firewall, proxy, and server state |
| Anonymous receives 200 on info | Overly broad permitAll config, wrong filter chain, or calling the wrong resource |
| Wrong password still gets 200 | Stale session/cookie or header, client auto-authenticating, or a public resource |
| Account lacking role gets 401 | Was the identity actually authenticated; are password/user source right |
| Account with sufficient role gets 403 | Actual authorities, ROLE_ prefix, selected chain, and proxy layers |
| Receives 302 then 200 | Check redirects, form login, and whether the client follows Location automatically |
| Receives 404 with right identity | Exposure, dependency, base-path, context-path, port, and handler |
| 200 but body is HTML | May be hitting a login page, gateway, or another resource |
| Only main port works | Check management context startup errors; do not assume the management port shares verified policies |
| POST gets 403 | Check CSRF and write-operation policy; do not alter roles based only on successful GETs |

### 10.1. Role-Based Permissions and Prefixes

`hasRole("ACTUATOR")` requires authority `ROLE_ACTUATOR`. If the identity source only grants authority `ACTUATOR`, they are not automatically equivalent. When using `hasAuthority`, write the exact authority value the system grants.

The operator account in the sample has a valid password yet lacks REPORT_READER, so 403 on the application port is the right result. Operations permissions are not implicitly business-read permissions.

### 10.2. Do Not Over-Infer From Status Codes

A 401 on `/actuator/env` does not prove env exists: security can run before handler lookup. Similarly, a 403 does not prove the error is in roles; write operations or intermediate layers can block for other reasons.

A 404 must also be tied to the URL and identity used. In the cross-port checks, the chosen account already passed the active policy so the missing handler is clearly visible.

### 10.3. Server/JDK Errors Are Not Authorization Results

If tests cannot start the server due to socket errors, you cannot report that the permission matrix was verified. For example, an `Unable to establish loopback connection` error occurring before accepting HTTP requests must be resolved in the JDK/OS environment and tests re-run.

Do not turn a startup error into a mock test and still claim both real HTTP ports passed verification. Goals and evidence types must match.

During verification with JDK 21.0.9 on Windows, an internal Unix socket connection error was resolved for the test session with the following JVM option, after which all 14 real HTTP runs succeeded:

```bash
mvn "-DargLine=-Djdk.net.unixdomain.tmpdir=./uds-directory-not-created" test
```

With this workaround, the `uds-directory-not-created` subdirectory must not exist. The JDK used in that verification pass falls back to an internal TCP connection mechanism when it cannot create a Unix socket in that directory. Both HTTP ports still open for real and requests still pass through authentication and authorization.

This is a verified workaround for the JDK/OS environment noted above, not an Actuator configuration property. If the environment runs normally, use the standard Maven command. For a different startup error, find that error's root cause instead of blindly applying the same option.

## 11. Re-Verifying in the Deployment Environment

The two loopback ports in this article are a learning environment. When deploying, apply the same matrix approach to real targets:

1. Direct application port if allowed to test.
2. Management port from the operations network or an authorized collector.
3. Public entrypoint through proxy/Ingress.
4. TLS paths, including hostname and CA chain validation.

A test run directly on the host does not prove another machine can reach that address. A test through a proxy also does not prove direct access to the management port is restricted if that port remains exposed.

With Basic, credentials must be protected when transmitted outside the learning environment. Do not skip certificate verification to make a test look successful. If infrastructure uses Bearer tokens or mTLS, keep the same three identity/permission groups while replacing credential generation and expected challenges per the real mechanism.

Record minimal evidence including target, test identity or role, status, and response content marker belonging to the right resource. Never save passwords, tokens, or Authorization headers into reports.

When changing `management.endpoints.web.base-path`, `management.server.base-path`, context-path, endpoint mappings, or adding health paths on the application port, update URLs and cross-port checks accordingly. The two 404 checks in this article reflect this sample's two-server layout, not a rule that all Actuator endpoints in every configuration exist only on the management port.

## 12. Self-Check Exercises

1. Run the 14-test suite. Explain why operator receives 403 on the API but 200 on Actuator info.
2. Change reporter's password in a manual call. Why is this an authentication test rather than a wrong-permission test?
3. Try calling the relative URL `/actuator/info` with a client bound to the application port and compare with an absolute URL using managementPort. Show how a test can hit the wrong target.
4. Change the required role for Actuator in the lab project. Which tests must fail before updating the expected matrix?
5. Change Actuator's base-path and update real URLs. Prove both the permission matrix and the two port-separation checks still hold under the new design.

You have verified completely when you know **which port the request reached, which identity was authenticated, which permission was checked, and which exact resource produced the response**, with tests that fail clearly if any of those changes unexpectedly.
