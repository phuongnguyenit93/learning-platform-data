# Build a writable management endpoint and security test suite

## 1. Practice goal and boundaries

A writable management endpoint does more than report information. It mutates application state, so you must verify who may invoke it, which HTTP methods are allowed, which payloads are accepted, and whether state stays unchanged when a request is rejected.

In this lab, we build an Actuator endpoint to toggle an **in-memory maintenance flag**:

```text
GET  /actuator/maintenance
     Reads enabled and revision
     Requires authority maintenance:read

POST /actuator/maintenance
     Writes enabled from JSON
     Requires authority maintenance:write and a valid CSRF token
```

Accompanied by:

- A simulated work API to observe the flag's effect.
- A route to obtain a CSRF token for the admin client.
- A test suite exercising Spring Security and real HTTP mappings inside the application context.

The example uses Spring Boot 3.3.x, Spring Security 6, the Servlet stack, and Java 17+. Operations modify only an object inside the JVM—no process shutdown, no file writes, and no external system edits. When the JVM restarts, state resets to defaults.

This is a practice model. If turning it into a real maintenance switch, design state persistence/sharing, operational permissions, and audit logging suited to a multi-instance system.

## 2. Distinguish registration, exposure, authentication, and write permission

There are four independent questions:

| Question | Mechanism in this lab |
| --- | --- |
| Does the endpoint exist? | A bean annotated with @Endpoint, with operations |
| Does the endpoint have an HTTP route? | HTTP exposure includes maintenance |
| Who does the request represent? | HTTP Basic |
| Is that identity allowed to act? | Method-specific authority, plus CSRF validation for POST |

`@WriteOperation` does not automatically grant management permissions. Enabling exposure does not automatically enable security either.

In Actuator under Spring Boot 3.3.x's model:

| Annotation | Typical HTTP method |
| --- | --- |
| @ReadOperation | GET |
| @WriteOperation | POST |
| @DeleteOperation | DELETE |

The Java method name does not automatically become a URL segment. The `update` method annotated with `@WriteOperation` on endpoint id `maintenance` is invoked via POST to `/actuator/maintenance`, not automatically to `/actuator/maintenance/update`.

The lab declares no DELETE operation. Never build state-mutating behavior behind GET just to make client calls easier.

## 3. Prepare dependencies and configuration

Use a Spring Boot 3.3.x project that already has a Gradle wrapper, Boot plugin, and Boot's dependency version management.

Required configuration snippet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'maintenance-endpoint-lab.jar'
}
```

This is a configuration snippet for a project that already has plugins, not a standalone build file. If build conventions already enable `-parameters`, keep the existing setup; the goal is preserving operation parameter names in bytecode.

Actuator needs parameter names to bind JSON fields to operation arguments. Do not assume every compiler retains parameter names without the corresponding flag.

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    maintenance:
      enabled: true
  endpoints:
    web:
      exposure:
        include: maintenance
```

The lab shares a local listener for the application and Actuator, keeping the default base path. Other Actuator endpoints do not need to be exposed for this goal.

Verify no other configuration source sets exposure exclude or changes ports/paths. When using a separate management port in another system, adjust the CSRF token path, cookie scope, and tests to match that architecture.

## 4. Separate business state from the Actuator layer

### 4.1. Startup class

File `src/main/java/demo/maintenance/MaintenanceApplication.java`:

```java
package demo.maintenance;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MaintenanceApplication {
    public static void main(String[] args) {
        SpringApplication.run(MaintenanceApplication.class, args);
    }
}
```

### 4.2. State and change revision

File `src/main/java/demo/maintenance/MaintenanceState.java`:

```java
package demo.maintenance;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceState {

    public record Snapshot(boolean enabled, long revision) {
    }

    private final AtomicReference<Snapshot> state =
            new AtomicReference<>(new Snapshot(false, 0));

    public Snapshot snapshot() {
        return state.get();
    }

    public Snapshot setEnabled(boolean enabled) {
        return state.updateAndGet(current ->
                current.enabled() == enabled
                        ? current
                        : new Snapshot(enabled, current.revision() + 1));
    }
}
```

An immutable Snapshot holds both enabled and revision. Reading a single object ensures both values belong to the same state snapshot.

`AtomicReference.updateAndGet` performs an atomic update within the JVM. The updater function may be retried under contention, so it only computes the new state without sending notifications or performing external side effects.

Revision increments only when enabled actually changes:

```text
Initial:       enabled=false, revision=0
Write true:    enabled=true,  revision=1
Write true:    enabled=true,  revision=1
Write false:   enabled=false, revision=2
```

Resending the same value is idempotent at the state level: it produces no further change. This does not turn POST in general into an HTTP method every infrastructure layer automatically treats as idempotent.

Revision in this lab is observational metadata, not an optimistic-locking guard via expectedRevision. If two callers write different values, updates are serialized atomically and the later write determines the final state. A system needing protection against overwriting operational decisions must design appropriate version checks.

### 4.3. Actuator endpoint

File `src/main/java/demo/maintenance/MaintenanceEndpoint.java`:

```java
package demo.maintenance;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "maintenance")
public class MaintenanceEndpoint {
    private final MaintenanceState state;

    public MaintenanceEndpoint(MaintenanceState state) {
        this.state = state;
    }

    @ReadOperation
    public MaintenanceState.Snapshot read() {
        return state.snapshot();
    }

    @WriteOperation
    public MaintenanceState.Snapshot update(boolean enabled) {
        return state.setEnabled(enabled);
    }
}
```

Valid JSON body:

```json
{"enabled":true}
```

Actuator binds the `enabled` field to the operation's primitive parameter and converts its type. The lab does not use an `@RequestBody` DTO like an MVC controller.

A required primitive boolean parameter rejects missing inputs. For requests that pass security, a body missing `enabled` or containing a non-boolean value must be rejected rather than silently treated as false.

Using a boolean type does not mean all complex validation cases are solved. If future operations have value ranges or business constraints, verify them explicitly; do not assume every MVC DTO validation annotation behaves identically on Actuator operations.

## 5. Create an API to observe the flag's effect

File `src/main/java/demo/maintenance/WorkController.java`:

```java
package demo.maintenance;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final MaintenanceState state;

    public WorkController(MaintenanceState state) {
        this.state = state;
    }

    @GetMapping("/lab/work")
    public ResponseEntity<String> work() {
        if (state.snapshot().enabled()) {
            return ResponseEntity.status(503).body("maintenance");
        }
        return ResponseEntity.ok("accepted");
    }
}
```

The controller uses the state service directly, without making HTTP calls to the management endpoint or depending on Actuator annotations.

This is a simulation: an in-flight request is not aborted when the flag changes; there is no traffic draining, queue closing, or transaction cancellation. Reading the flag at one instant only determines the processing branch for that request at that read point.

Do not use this flag as a mechanical replacement for orchestrator liveness/readiness probes. Those signals must be designed around actual serving capability.

## 6. Security: separate read/write permissions and keep CSRF

Create three accounts:

| Account | Authorities | Permissions |
| --- | --- | --- |
| reader | maintenance:read | Read status, fetch CSRF token |
| writer | maintenance:read, maintenance:write | Read, write with valid CSRF token |
| app | app:use | Call work API; no management permissions |

These are full authority strings, so the code uses `hasAuthority` without prepending `ROLE_`.

Application passwords are read from the environment. Dummy passwords in the tests below are test fixtures only, not deployment passwords.

File `src/main/java/demo/maintenance/SecurityConfiguration.java`:

```java
package demo.maintenance;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

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
        var reader = User.withUsername("reader")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_READER_PASSWORD")))
                .authorities("maintenance:read")
                .build();

        var writer = User.withUsername("writer")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_WRITER_PASSWORD")))
                .authorities("maintenance:read", "maintenance:write")
                .build();

        var app = User.withUsername("app")
                .password(encoder.encode(
                        environment.getRequiredProperty("LAB_APP_PASSWORD")))
                .authorities("app:use")
                .build();

        return new InMemoryUserDetailsManager(reader, writer, app);
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        RequestMatcher endpoint =
                EndpointRequest.to(MaintenanceEndpoint.class);

        RequestMatcher read = new AndRequestMatcher(
                endpoint,
                request -> "GET".equals(request.getMethod()));

        RequestMatcher write = new AndRequestMatcher(
                endpoint,
                request -> "POST".equals(request.getMethod()));

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(read)
                        .hasAuthority("maintenance:read")
                        .requestMatchers(write)
                        .hasAuthority("maintenance:write")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/ops/csrf")
                        .hasAnyAuthority(
                                "maintenance:read", "maintenance:write")
                        .requestMatchers(HttpMethod.GET, "/lab/work")
                        .hasAuthority("app:use")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

### 6.1. Filter chain selection and HTTP method restriction

The Actuator filter chain runs first and matches Actuator endpoints. Inside it, matchers combine the specific endpoint with the HTTP method, so read permission never turns into write permission.

The fallback filter chain protects remaining requests. Configuring only a chain matching Actuator without verifying how requests outside it are protected can leave other HTTP surfaces exposed.

Rules across multiple filter chains are not combined for the same request; the first matching chain in order wins. Placing a catch-all chain first can shadow the management filter chain.

EndpointRequest tracks endpoint paths from Boot configuration. It neither replaces authentication nor inspects TCP ports.

### 6.2. Why does Basic authentication still need CSRF?

CSRF is the risk of a browser sending a request with credentials automatically attached from an existing context. HTTP Basic does not eliminate this risk, because browsers can cache and resend Basic credentials.

The lab keeps Spring Security's default CSRF protection on both filter chains. There is no `csrf.disable()` or blanket exemption for Actuator paths.

CSRF tokens and authorities solve two distinct questions:

- A valid token does not grant `maintenance:write` to `reader`.
- Holding `maintenance:write` does not make a POST missing a token valid.

CORS is also a separate mechanism. A passing curl request does not test browser CORS policy; toggling CORS is not a substitute for CSRF checks.

### 6.3. Filter order affects status codes

Do not apply a blanket rule that “every unauthenticated request returns 401” to all POSTs. CsrfFilter may reject an unsafe method such as POST before authentication runs, so a POST without a token can return 403 even with no identity.

The test suite separates:

- Unauthenticated GET to verify 401.
- Unauthenticated POST with valid CSRF to verify 401.
- Writer POST missing/invalid CSRF to verify 403.
- Reader POST with valid CSRF to verify missing write permission.

This separation avoids seeing a 403 and falsely assuming the account was already authenticated.

## 7. Issue CSRF tokens for the admin client

The lab uses the default CSRF repository storing tokens in the HTTP session. Clients fetch the token, preserve the session cookie, and send the token back in the matching header on POST. That is why this lab does not set STATELESS session policy.

File `src/main/java/demo/maintenance/OpsCsrfController.java`:

```java
package demo.maintenance;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpsCsrfController {

    @GetMapping("/ops/csrf")
    public ResponseEntity<Map<String, String>> token(CsrfToken csrfToken) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", csrfToken.getHeaderName(),
                        "token", csrfToken.getToken()));
    }
}
```

This endpoint is a client-helper controller, not an Actuator operation. It is protected by the fallback filter chain and permits only authorized management identities to fetch tokens.

The token is dynamic and may be masked according to Spring Security's token handling. Clients use the returned `token` and `headerName` rather than guessing token format or hardcoding a fixed string.

Do not log tokens or cookies. A token does not replace credentials; the example requests still send HTTP Basic. If a session expires or a token becomes invalid, the client must fetch a fresh token via the designed flow.

When deploying beyond loopback, protect transport with TLS or an appropriate channel. HTTP Basic uses Base64, which provides no confidentiality on the wire.

## 8. Security integration test suite

Use `@SpringBootTest` and MockMvc with security filters enabled to test Actuator mapping, input binding, and filter chains together. Do not set `addFilters=false`, as that removes the very thing under test.

File `src/test/java/demo/maintenance/MaintenanceSecurityTest.java`:

```java
package demo.maintenance;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "LAB_READER_PASSWORD=reader-test-pass",
        "LAB_WRITER_PASSWORD=writer-test-pass",
        "LAB_APP_PASSWORD=app-test-pass"
})
@AutoConfigureMockMvc
class MaintenanceSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MaintenanceState state;

    @Autowired
    ObjectMapper objectMapper;

    @BeforeEach
    void startWithMaintenanceDisabled() {
        state.setEnabled(false);
    }

    @Test
    void readAccessIsSeparatedAndGetDoesNotWrite() throws Exception {
        var before = state.snapshot();

        mvc.perform(get("/actuator/maintenance"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass"))
                        .param("enabled", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false))
                .andExpect(jsonPath("$.revision").isNumber());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isForbidden());

        assertEquals(before, state.snapshot());
    }

    @Test
    void csrfAndWritePermissionAreIndependent() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf().useInvalidToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("app", "app-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());

        assertEquals(before, state.snapshot());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "wrong-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());

        assertEquals(before, state.snapshot());
    }

    @Test
    void writerCanChangeStateAndRepeatTheSameValue() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));

        var changed = state.snapshot();
        assertEquals(before.revision() + 1, changed.revision());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk());

        assertEquals(changed, state.snapshot());

        mvc.perform(get("/actuator/maintenance")
                        .with(httpBasic("reader", "reader-test-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));
    }

    @Test
    void invalidInputNeverChangesState() throws Exception {
        var before = state.snapshot();

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":\"not-a-boolean\"}"))
                .andExpect(status().isBadRequest());

        assertEquals(before, state.snapshot());
    }

    @Test
    void realTokenAndSessionRoundTripAllowsWrite() throws Exception {
        var tokenResult = mvc.perform(get("/ops/csrf")
                        .with(httpBasic("writer", "writer-test-pass")))
                .andExpect(status().isOk())
                .andReturn();

        var json = objectMapper.readTree(
                tokenResult.getResponse().getContentAsString());

        String headerName = json.get("headerName").asText();
        String token = json.get("token").asText();

        var session = (MockHttpSession)
                tokenResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/actuator/maintenance")
                        .session(session)
                        .with(httpBasic("writer", "writer-test-pass"))
                        .header(headerName, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(true));

        assertEquals(true, state.snapshot().enabled());
    }

    @Test
    void workApiFollowsTheAuthorizedStateChange() throws Exception {
        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("accepted"));

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":true}"))
                .andExpect(status().isOk());

        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().string("maintenance"));

        mvc.perform(post("/actuator/maintenance")
                        .with(httpBasic("writer", "writer-test-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"enabled\":false}"))
                .andExpect(status().isOk());

        mvc.perform(get("/lab/work")
                        .with(httpBasic("app", "app-test-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("accepted"));
    }
}
```

### 8.1. Why not just call the update method directly?

Calling `endpoint.update(true)` directly can test state-change logic, but it fails to test:

- HTTP mapping of WriteOperation.
- JSON binding and Content-Type handling.
- Security filter chains.
- Authentication and authorities.
- CSRF.

MockMvc here exercises those layers inside the application context. It still does not replace testing over a real listener, TLS, reverse proxy, or firewall.

### 8.2. Why include both csrf() and the real token flow?

`csrf()` from spring-security-test lets you isolate authentication, permissions, and binding. It does not by itself prove a real admin client can fetch a token and return it in the same session.

The `realTokenAndSessionRoundTripAllowsWrite` test does not use the csrf helper on POST. It fetches the token from the controller, keeps the session, and sends the token in the header, thus also exercising the lab's actual token-exchange contract.

Do not rely on `@WithMockUser` as sole proof that application passwords are checked. The suite uses `httpBasic` to exercise the configured authentication mechanism.

### 8.3. Keep tests independent of execution order

BeforeEach resets enabled to false without forcing revision to 0. Tests capture the initial Snapshot and compare deltas or invariance.

Thus there is no need to assume JUnit executes test methods in a specific order. Because this suite shares state inside the application context, do not configure its methods to run in parallel without adding isolation.

In particular, tests for rejected requests must assert Snapshot did not change, not only assert the HTTP status code. An error response is not sufficient proof that side effects were prevented.

### 8.4. Run the tests

```bash
./gradlew test
```

On Windows use `gradlew.bat test`. For multi-project builds, use the task path for the specific module.

The required outcome is all seven tests passing. Console formatting, runtime, and startup logs depend on the environment; do not treat them as fixed stdout. Passwords ending in `test-pass` in the code above are dummy fixtures for testing only.

## 9. Outcome matrix to satisfy

With the lab configuration:

| Request | Condition | Expected |
| --- | --- | --- |
| GET maintenance | Unauthenticated | 401 |
| GET maintenance | reader, valid password | 200, reads Snapshot |
| GET maintenance | app, valid password | 403 |
| GET maintenance?enabled=true | reader | 200, state unchanged |
| POST maintenance | writer, missing CSRF | 403, state unchanged |
| POST maintenance | writer, invalid CSRF | 403, state unchanged |
| POST maintenance | reader, valid CSRF | 403, state unchanged |
| POST maintenance | app, valid CSRF | 403, state unchanged |
| POST maintenance | Unauthenticated, valid CSRF | 401, state unchanged |
| POST maintenance | writer wrong password, valid CSRF | 401, state unchanged |
| POST maintenance | writer, valid CSRF, valid body | 200, changed per body |
| POST maintenance | writer, valid CSRF, missing/invalid enabled | 400, state unchanged |

A binding test must supply valid authentication and CSRF; otherwise the request can be blocked before body parsing and the test has not actually tested binding.

Similarly, to test reader's write permission, supply valid CSRF. If reader lacks a token and gets 403, you cannot conclude the authority rule was enforced yet.

## 10. Run the application locally

The PowerShell example below prompts for passwords without echoing them to the terminal. Use non-empty passwords; to keep HTTP Basic tests reproducible across clients, you can choose ASCII strings during the lab session.

```powershell
$labReaderSecret = Read-Host "Password for reader" -AsSecureString
$env:LAB_READER_PASSWORD = [System.Net.NetworkCredential]::new("", $labReaderSecret).Password

$labWriterSecret = Read-Host "Password for writer" -AsSecureString
$env:LAB_WRITER_PASSWORD = [System.Net.NetworkCredential]::new("", $labWriterSecret).Password

$labAppSecret = Read-Host "Password for app" -AsSecureString
$env:LAB_APP_PASSWORD = [System.Net.NetworkCredential]::new("", $labAppSecret).Password

.\gradlew.bat bootJar
java -jar build/libs/maintenance-endpoint-lab.jar
```

On Bash, set the corresponding three environment variables and run `./gradlew bootJar`. Never put real password values into source or command arguments stored in shell history.

The application classes require framework dependencies. `java -jar` runs the executable JAR; do not compile individual files with `javac` while omitting the Spring Boot classpath.

Keep the process running and open another terminal for checks. On Windows, use `curl.exe` to avoid PowerShell's alias. Pass only the username to `--user` so curl prompts for the password.

On a fresh process, read status:

```powershell
curl.exe -i --user reader http://127.0.0.1:8080/actuator/maintenance
```

Expect HTTP 200 with equivalent JSON:

```json
{"enabled":false,"revision":0}
```

JSON field order and HTTP headers are not fixed contracts. Do not predict timestamps or full startup logs.

Check the work API:

```powershell
curl.exe -i --user app http://127.0.0.1:8080/lab/work
```

When the flag is false, body is `accepted`, HTTP 200. The code adds no trailing newline to the body.

## 11. Send POST with CSRF through a real client flow

This section uses PowerShell to parse JSON, requiring no extra JSON parsing tools. The created files are solely for the local client; cookies and CSRF tokens must stay scoped to the lab session.

### 11.1. Fetch the token and keep cookies

```powershell
curl.exe --fail --silent --show-error --user writer --cookie-jar maintenance-lab-cookies.txt --output maintenance-lab-csrf.json http://127.0.0.1:8080/ops/csrf

$labCsrf = Get-Content -LiteralPath maintenance-lab-csrf.json -Raw | ConvertFrom-Json
```

Enter the writer password when curl prompts. If curl errors, resolve the error before reading the file; do not continue using a stale token file from another session.

Having the controller access the token causes the token to be generated/saved by the lab's repository. The session cookie lets the next request locate the matching token on the server.

### 11.2. Prepare the body and send the write

Use a body file to avoid JSON quoting differences across shells:

```powershell
Set-Content -LiteralPath maintenance-lab-write.json -Value '{"enabled":true}' -Encoding Ascii -NoNewline

curl.exe -i --user writer --cookie maintenance-lab-cookies.txt --header "$($labCsrf.headerName): $($labCsrf.token)" --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

`--data-binary` makes the request use POST. The token header uses values from the response, rather than hardcoding a guessed token.

On a fresh process with no prior changes, expect HTTP 200 with equivalent JSON:

```json
{"enabled":true,"revision":1}
```

Resending the same value in the same state does not increment revision. If the session/token expires or changes after authentication events, fetch a new token; do not weaken security rules to mask a client session-management bug.

### 11.3. Verify after the write

```powershell
curl.exe -i --user reader http://127.0.0.1:8080/actuator/maintenance
curl.exe -i --user app http://127.0.0.1:8080/lab/work
```

Reader can still read status but lacks write permission. The work API returns HTTP 503 and body `maintenance` while the flag is enabled.

To restore, change the body to false, reuse the valid token/session, and POST:

```powershell
Set-Content -LiteralPath maintenance-lab-write.json -Value '{"enabled":false}' -Encoding Ascii -NoNewline

curl.exe -i --user writer --cookie maintenance-lab-cookies.txt --header "$($labCsrf.headerName): $($labCsrf.token)" --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

If only the two transitions false→true→false occurred, the final Snapshot has enabled=false, revision=2, and the work API returns accepted again.

### 11.4. Test a write request without a token

Still send the writer password, but omit the cookie/CSRF header:

```powershell
curl.exe -i --user writer --header "Content-Type: application/json" --data-binary "@maintenance-lab-write.json" http://127.0.0.1:8080/actuator/maintenance
```

Expect 403. Read Snapshot before and after to verify nothing changed. This request tests CSRF, not that writer lacks write permission.

Do not hardcode tokens in source, put tokens in URLs, or include full cookies/tokens in logs or report screenshots.

## 12. Diagnose unexpected results

| Symptom | Check in order |
| --- | --- |
| App fails to start due to missing property | Are the three environment variables set on the running Java process? |
| 404 on endpoint path | @Endpoint bean, id, enablement, exposure, base path, and right instance |
| 404 on /maintenance/update | Java method names do not create URLs; POST to the endpoint root |
| 401 when reading as writer | Username/password and effective HTTP Basic configuration |
| 403 when writer POSTs | Is the token valid, cookie matching session, and which filter chain handled it? |
| 403 for reader with valid token | Expected: reader lacks maintenance:write |
| 400 even though body looks valid | Content-Type, `enabled` name, type conversion, and `-parameters` metadata |
| 415 | Sent media type does not match the operation |
| 405 or rejected for other HTTP methods | Which operations are declared and security rules for that method |
| POST returns error yet state changed | Check whether side effects ran before rejection or failed after write; test state |
| Writing true succeeds yet another instance stays false | State in this lab lives only in one JVM's memory |
| GET shows stale value after adding caching | Check read-operation TTL/cache and required consistency |
| Tests pass but curl fails | Compare CSRF helper vs real token/session flow, artifact, and HTTP infra |

A 404 from a proxy or a 403 before binding does not prove parameters were validated. Identify the actual layer returning the error via controlled logging and observed responses.

When Spring Security logs are needed, enable them only during the diagnostic session. Never print Authorization headers, passwords, cookies, or tokens. After changing filter chains or matchers, re-run both allow and deny tests; a shared rule can break multiple paths at once.

Do not use a direct method call as proof that “the endpoint is secure,” and do not use a test that only asserts HTTP status as proof that side effects were prevented.

## 13. Decisions needed before using outside the lab

### Multi-instance state and durability

AtomicReference solves contention within one JVM only. It neither synchronizes across replicas nor survives restarts.

If the flag must apply cluster-wide, use a durable/shared state store with explicit update, versioning, and error-handling mechanisms. One instance's response does not prove all instances updated.

### Operational audit logs and accountability

An operationally significant write should record who requested it, when, before/after values, and outcome per system policy. Do not include tokens or credentials in that audit record.

If adding auditing to a CAS update function later, do not perform external log shipping or database writes inside an update callback that can retry. Design audit placement and consistency around real transactions.

This lab implements neither durable audit logging, approval workflows, nor distributed rollback; those capabilities must not be assumed merely from having write permission.

### Protect every exposed channel properly

SecurityFilterChain in this lab protects HTTP Servlet traffic. If an endpoint is also exposed over JMX or another management channel, secure that channel separately. HTTP exposure is not a blanket security policy across all transports.

Likewise, permissions on a reverse proxy do not protect a backend port that remains directly reachable. Verify actual request paths during deployment.

### Client design and operation types

Keeping CSRF in this lab's Basic/session model is an intentional choice. If moving to a management API using bearer tokens with a different client model, re-evaluate how credentials are sent and CSRF exposure before changing settings; do not disable CSRF across endpoints by copying an example with different assumptions.

Heavy or long-running operations need separate contracts for timeouts, job status, and idempotency. Do not put unbounded work inside a synchronous management request and treat HTTP 200 as sufficient.

## 14. Acceptance and cleanup

The lab is complete when:

1. GET only reads and never mutates state even with write-like query parameters.
2. POST binds `enabled` from JSON and returns the post-operation Snapshot.
3. Reader cannot write even with valid CSRF.
4. Writer cannot write when CSRF is missing/invalid.
5. Valid CSRF does not substitute for authentication.
6. Missing/invalid input is rejected with Snapshot unchanged.
7. Rewriting the same value does not increment revision.
8. The test suite covers both the CSRF helper and a real token/session round-trip.
9. The simulated API changes behavior after an authorized write and recovers when disabled.
10. Single-JVM state limits and HTTP protection scope are clearly documented.

At session end, restore the flag to false if the process is still in use, stop the application, and remove client files created in the test directory:

```powershell
Remove-Item -LiteralPath maintenance-lab-cookies.txt,maintenance-lab-csrf.json,maintenance-lab-write.json
Remove-Item Env:LAB_READER_PASSWORD
Remove-Item Env:LAB_WRITER_PASSWORD
Remove-Item Env:LAB_APP_PASSWORD
```

Delete only those lab files in the directory where you created them. Clearing environment variables in the terminal does not strip the environment of an already running Java process; stop the process separately.

The core evidence is that each request triggers side effects only after passing every designed gate, and rejected requests leave state untouched. Your test suite must verify both sides.
