# Protecting heapdump, logfile, env, and State-Changing Endpoints

## 1. Actuator Is a Management Plane

Actuator provides observability and control over a running application. Capabilities useful to operators can also become data exfiltration or disruption vectors if permissions are overly broad.

Two risk groups must be distinguished:

- **Information disclosure:** downloading JVM heap memory, reading logs, or inspecting configuration.
- **State mutation:** changing log levels, clearing cache entries, terminating sessions, or shutting down the application.

A GET request may not modify business data yet still be highly sensitive. For example, someone permitted to download a heap dump can obtain far more in-memory data than someone only permitted to call business APIs. Protecting Actuator therefore cannot stop at a “GET for everyone, POST for admins” rule.

This article uses **Spring Boot 3.3.x, Spring Security 6.3.x, Java 21, Servlet/Spring MVC**. The hands-on assumes Actuator and the application share a port, prefix `/actuator`, with no path-rewriting proxy. This is an example for a standalone test project, not a configuration to apply verbatim to every application.

## 2. Understanding the Risk of Each Endpoint

### 2.1. Heapdump: Permission to View a Memory Snapshot

`GET /actuator/heapdump` generates and returns a JVM heap dump. The format depends on the JVM; HotSpot typically uses HPROF. The binary response can be very large; see [heapdump 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

From those traits, evaluate two consequences:

1. **Data:** password strings, tokens, request payloads, user data, or decrypted objects can still reside in memory. There is no guarantee every secret appears, yet this file must never be treated as a harmless statistic.
2. **Resources:** capturing, writing, and transferring the dump consumes resources; concrete impact depends on heap size, JVM, and application load. Do not use this endpoint as a periodic health probe.

Permission to download heap dumps should be a separate privilege, granted only for a defined diagnostic need. A routine log-reading account does not implicitly need this permission.

Masking values in `/env` does not sanitize heapdump contents. If a secret actually exists in the process, masking its value in a JSON response does not remove it from memory.

### 2.2. Logfile: Permission to Read Application History

`GET /actuator/logfile` returns log file contents; with Spring MVC you can use the `Range` header to read a slice. Logfile exists only when the application has an appropriate log file source, such as `logging.file.name` or corresponding external file configuration. See [logfile 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html) and [endpoint catalog](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

If the application only writes to stdout, adding `logfile` to exposure does not automatically turn platform/container logs into a downloadable file.

Logs can contain user identifiers, paths, parameters, stack traces, SQL queries, or program-logged data. Protection must go hand in hand with logging discipline: avoid logging Authorization headers, cookies, passwords, access tokens, or full request bodies containing private data.

`Range: bytes=0-1023` only changes the byte range fetched, without reducing authorization requirements. Someone disallowed from reading the full log must not read slices and reassemble them either.

### 2.3. Env: Masking Values Does Not Mean Hiding System Structure

`GET /actuator/env` returns Environment information; `/actuator/env/{property.name}` queries a single property. Information can include property sources, profiles, and property origins. See [env 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

Even when values are masked, property names, profiles, property source names, or source paths can still reveal deployment details. Therefore, you may need to restrict the whole endpoint, not just mask keys named password.

In Spring Boot 3.3, `management.endpoint.env.show-values` controls showing values:

| Value | Meaning |
| --- | --- |
| `never` | Mask values |
| `when-authorized` | Show only under the endpoint's authorization condition |
| `always` | Allow showing values, unless a custom sanitizing function continues to mask them |

If using `when-authorized`, configure endpoint roles carefully; by default, authenticated users may be treated as authorized to view values. **Value-viewing conditions and URL access permissions are two different things.** Setting `show-values: never` does not block URL access; setting `roles` on the endpoint does not replace Spring Security HTTP rules either.

Do not set `always` just to speed up quick diagnostics. The hands-on lab keeps `never` even for users authorized to read env. This mechanism is described in [sanitizing sensitive values](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

### 2.4. State-Changing Endpoints

| Operation | Impact to consider |
| --- | --- |
| `POST /actuator/loggers/{name}` | Changes log level; can increase load, storage, and sensitive data logged |
| `DELETE /actuator/caches/{name}` | Clears cache entries; can increase load on data sources or alter behavior temporarily |
| `POST /actuator/shutdown` | Shuts down the application if the endpoint is enabled and available |
| Deleting sessions via `sessions` endpoint when Spring Session is present | Can forcibly invalidate user sessions |

[Loggers API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html) describes POST with `configuredLevel`; [shutdown API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) describes the stop operation. Do not treat permission to read logger config as permission to modify it.

In plain Spring Boot Actuator 3.3, `env` is a read-only endpoint. Do not assume `POST /actuator/env` exists to update configuration based on Spring Cloud examples or custom endpoints from another system. Inventory the exact dependencies and operations of the application you are securing.

## 3. Four Complementary Protection Layers

| Layer | Decision |
| --- | --- |
| Existence | Which endpoints are enabled and satisfy bean creation conditions? |
| Protocol exposure | Which endpoints appear over HTTP or JMX? |
| Request authorization | Which identity may use which HTTP method on which endpoint? |
| Operations and data | Who collects, stores, views, forwards, and deletes diagnostic outputs? |

`enabled` and exposure are not synonymous. Omitting an endpoint from HTTP exposure does not guarantee it is also disabled on another channel. Conversely, `permitAll()` does not give a disabled endpoint a handler.

For exposure configuration, exclude lists take precedence over include lists. If base config excludes `heapdump`, merely adding it to `include` in another profile may not expose it. Inspect the effective configuration, not just one YAML file.

Disabling the discovery page or renaming `/actuator` only reduces accidental discovery of paths. It does not authenticate or authorize requests that already know the URL.

Good practice is exposing only the minimal endpoints needed, defining explicit permissions, and denying unreviewed cases by default.

## 4. Baseline Configuration: Expose Only health

Below is `src/main/resources/application.yml` of a test project:

~~~yaml
spring:
  application:
    name: sensitive-actuator-lab
  jmx:
    enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      show-details: never
    heapdump:
      enabled: false
    logfile:
      enabled: false
    env:
      enabled: false
    loggers:
      enabled: false
    caches:
      enabled: false
    shutdown:
      enabled: false
~~~

The example expresses the intent not to use sensitive capabilities in baseline mode. It does not merely hide UI links.

JMX is a separate channel: HTTP config and Servlet `SecurityFilterChain` do not control MBean invocations. `spring.jmx.enabled` affects Spring-managed mechanisms and does not necessarily disable every MBean or management channel provided by libraries/the JVM itself; see [management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Do not rely solely on getting 404 to prove an endpoint is disabled. A security filter can return 401/403 before MVC determines there is no handler. Cross-check effective configuration, relevant mappings/beans, and access behavior.

## 5. Hands-On Authorization on a Local Profile

This section creates two accounts:

- `analyst`: reads masked env and reads logfile.
- `operator`: reads/changes log levels and reads/clears cache data.

**Do not create an account with heapdump permission by default.** The heapdump rule is still declared so a dedicated authority is required when a system genuinely grants controlled diagnostic access.

Do not use one generic ADMIN role for all operations. The following authority names are this example's design, not authority names auto-created by Spring Boot.

### 5.1. Dependencies and Application

The project requires Java 21, Spring Boot 3.3.x plugin, dependency management, and Gradle Wrapper. Required declarations in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Java files below live under `src/main/java/com/example/actuatorguard/`. They are Spring code in a project with dependencies, not single-file programs run with javac.

`GuardApplication.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class GuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(GuardApplication.class, args);
    }

    @Bean
    @Profile("actuator-lab")
    CacheManager labCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
~~~

CacheManager lets us test the effect of clearing cache entries without connecting a database.

### 5.2. Open Diagnostic Capabilities Only in the Test Profile

Create `src/main/resources/application-actuator-lab.yml`:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,env,logfile,heapdump,loggers,caches
  endpoint:
    env:
      enabled: true
      show-values: never
    logfile:
      enabled: true
    heapdump:
      enabled: true
    loggers:
      enabled: true
    caches:
      enabled: true
    shutdown:
      enabled: false

logging:
  file:
    name: .actuator-lab/log/application.log
  level:
    com.example.actuatorguard.probe: INFO

lab:
  reader-password: ${LAB_READER_PASSWORD}
  operator-password: ${LAB_OPERATOR_PASSWORD}
  marker: safe-marker-not-a-secret
~~~

The profile overrides the needed `enabled` flags. Exposure does not use `*`. JMX config and shutdown disablement still inherit from the baseline file.

Heapdump is included in the profile to test the denied branch; **do not run a command to download heapdump** in this article. A JVM that does not support heapdump or an environment missing prerequisites might not create the corresponding operation.

Profiles are a configuration selection tool, not an authentication boundary. Do not activate a test profile in real environments and treat it as a complete operational policy.

### 5.3. Accounts Strictly for the Experiment

`LabAccounts.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration(proxyBeanMethods = false)
@Profile("actuator-lab")
public class LabAccounts {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${lab.reader-password}") String readerPassword,
            @Value("${lab.operator-password}") String operatorPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("analyst")
                .password(encoder.encode(readerPassword))
                .authorities("ACTUATOR_ENV_READ", "ACTUATOR_LOG_READ")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .authorities(
                    "ACTUATOR_LOGGERS_READ",
                    "ACTUATOR_LOGGERS_WRITE",
                    "ACTUATOR_CACHES_READ",
                    "ACTUATOR_CACHES_CLEAR")
                .build()
        );
    }
}
~~~

Both passwords come from environment variables. Do not use these accounts as an identity management template for real production. For operational systems, map authorities through a managed identity source with proper grant/revocation mechanisms.

### 5.4. Authorizing by Endpoint and HTTP Method

`ActuatorSecurity.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurity {
    private static RequestMatcher operation(String method, String... ids) {
        return new AndRequestMatcher(
            EndpointRequest.to(ids),
            request -> method.equals(request.getMethod())
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(operation("GET", "health")).permitAll()
                .requestMatchers(operation("GET", "heapdump"))
                    .hasAuthority("ACTUATOR_HEAPDUMP_READ")
                .requestMatchers(operation("GET", "logfile"))
                    .hasAuthority("ACTUATOR_LOG_READ")
                .requestMatchers(operation("GET", "env"))
                    .hasAuthority("ACTUATOR_ENV_READ")
                .requestMatchers(operation("GET", "loggers"))
                    .hasAuthority("ACTUATOR_LOGGERS_READ")
                .requestMatchers(operation("POST", "loggers"))
                    .hasAuthority("ACTUATOR_LOGGERS_WRITE")
                .requestMatchers(operation("GET", "caches"))
                    .hasAuthority("ACTUATOR_CACHES_READ")
                .requestMatchers(operation("DELETE", "caches"))
                    .hasAuthority("ACTUATOR_CACHES_CLEAR")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

Points to read from the code:

- `securityMatcher` selects the applicable chain; inner matchers select permissions for requests inside that chain.
- The helper combines endpoint and method. GET loggers does not grant POST; GET caches does not grant DELETE.
- Endpoint matchers cover subpaths such as `/env/lab.marker` and `/caches/books`. That is why you must not test only a single root URL.
- The Range header does not change permissions: it is still a GET to logfile.
- `anyRequest().denyAll()` blocks unhandled cases, including endpoints exposed later.
- The fallback chain protects non-Actuator URLs. Real applications must replace it with their own business policy.
- Only the first matching chain is used; chains do not stack.

The example intentionally permits only GET for reading. HEAD is not automatically granted; do not use HEAD on heapdump as a cheap check because the GET handler can still execute to construct the response.

`hasAuthority` uses the exact authority name. `hasRole` applies the ROLE_ prefix convention; do not swap the two methods while keeping the same authority strings.

Matcher APIs can be cross-checked in [EndpointRequest 3.3 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.java). Chain selection and request authorization are covered in [Spring Security Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) and [HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

### 5.5. Valid Authentication Can Still Be Blocked by CSRF

The configuration keeps CSRF. Operator sending POST with the right password but missing a token can still receive 403. A valid CSRF token grants no extra authority; analyst with a token still cannot change log levels.

Do not disable CSRF app-wide just to fix a test command. If moving machine routes to accept only Bearer headers, verify they accept no auto-sent identities via cookies/Basic before choosing a scoped exemption. Merely labeling stateless is not enough proof. Default mechanics are described in [Servlet CSRF branch 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/docs/modules/ROOT/pages/servlet/exploits/csrf.adoc).

The tests below use MockMvc's CSRF helper to focus on proving permissions and effects. A real operations UI also needs a token retrieval/submission flow tailored to its session and frontend.

## 6. Testing Read Permissions Without Downloading a Heapdump

Run the test project from PowerShell:

~~~powershell
$env:LAB_READER_PASSWORD = 'local-reader-only'
$env:LAB_OPERATOR_PASSWORD = 'local-operator-only'
.\gradlew.bat bootRun --args="--spring.profiles.active=actuator-lab"
~~~

Use local test passwords, never real accounts. Open a second terminal:

~~~powershell
$base = 'http://127.0.0.1:8080'

function New-LabBasicHeader([string]$account, [string]$password) {
    $bytes = [Text.Encoding]::UTF8.GetBytes("${account}:$password")
    @{ Authorization = 'Basic ' + [Convert]::ToBase64String($bytes) }
}

$reader = New-LabBasicHeader 'analyst' 'local-reader-only'
$operator = New-LabBasicHeader 'operator' 'local-operator-only'

$envResult = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/actuator/env/lab.marker" -Headers $reader
$envResult.StatusCode
($envResult.Content | ConvertFrom-Json).property.value
~~~

Expected:

~~~text
200
******
~~~

Asterisks are the result of value masking, even though marker is only synthetic data. Permission to read env does not automatically enable showing raw values.

Switch to operator to verify denial:

~~~powershell
try {
    Invoke-WebRequest -UseBasicParsing `
        -Uri "$base/actuator/env/lab.marker" -Headers $operator |
        Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}
~~~

Expected `403`: operator is granted permission to control certain operations, not permission to read env.

Expected matrix for the test profile:

| Request | Unauthenticated | Analyst | Operator |
| --- | --- | --- | --- |
| GET health when app is healthy | 200 | 200 | 200 |
| GET env and env/property | 401 | 200, values masked | 403 |
| GET logfile, with or without valid Range | 401 | Readable | 403 |
| GET heapdump | 401 | 403 | 403 |
| POST loggers with valid CSRF, valid payload | 401 | 403 | 204 |
| DELETE cache books with valid CSRF | 401 | 403 | 204 |

Write/delete rows assume valid tokens to isolate identity and permission checks. Missing tokens can return 403 before authentication checks. Full log reads typically return 200; satisfied Range requests may return 206. A missing file or invalid Range alters the result.

Do not automatically download a heapdump just to “test success”. The denied branch verifies both accounts' permissions without creating memory files. To verify the allowed branch, use a dedicated test with synthetic data and a bounded resource budget.

## 7. Regression Tests for Permission Boundaries

Create `src/test/java/com/example/actuatorguard/ActuatorGuardTest.java`:

~~~java
package com.example.actuatorguard;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.logging.LoggingSystem;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("actuator-lab")
@SpringBootTest(properties = {
    "lab.reader-password=reader-test-only",
    "lab.operator-password=operator-test-only",
    "logging.file.name=${java.io.tmpdir}/actuator-guard-test.log"
})
@AutoConfigureMockMvc
class ActuatorGuardTest {
    private static final String PROBE = "com.example.actuatorguard.probe";
    private static final String LOGGER = "/actuator/loggers/" + PROBE;
    private static final String BODY = "{\"configuredLevel\":\"DEBUG\"}";

    @Autowired MockMvc mvc;
    @Autowired CacheManager cacheManager;
    @Autowired LoggingSystem loggingSystem;

    private Cache books;

    @BeforeEach
    void prepareState() {
        books = cacheManager.getCache("books");
        assertNotNull(books);
        books.put("isbn", "draft");
        loggingSystem.setLogLevel(PROBE, LogLevel.INFO);
    }

    @Test
    void anonymousCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void analystReadsMaskedEnvironment() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.property.value").value("******"));
    }

    @Test
    void operatorCannotReadEnvironmentSubpath() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCanReadLogFile() throws Exception {
        mvc.perform(get("/actuator/logfile")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isOk());
    }

    @Test
    void rangeDoesNotBypassLogPermission() throws Exception {
        mvc.perform(get("/actuator/logfile")
                .header("Range", "bytes=0-15")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotDownloadHeap() throws Exception {
        mvc.perform(get("/actuator/heapdump")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotWriteLoggerEvenWithCsrf() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("analyst", "reader-test-only"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
        assertEquals(LogLevel.INFO,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void operatorNeedsCsrfForLoggerWrite() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("operator", "operator-test-only"))
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
        assertEquals(LogLevel.INFO,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void operatorCanChangeLoggerWithCsrf() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("operator", "operator-test-only"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isNoContent());
        assertEquals(LogLevel.DEBUG,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void rejectedDeleteKeepsCacheData() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
        assertNotNull(books.get("isbn"));
    }

    @Test
    void authorizedDeleteClearsCacheData() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("operator", "operator-test-only"))
                .with(csrf().asHeader()))
            .andExpect(status().isNoContent());
        assertNull(books.get("isbn"));
    }

    @Test
    void unlistedActuatorUrlIsDenied() throws Exception {
        mvc.perform(get("/actuator/beans")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~powershell
.\gradlew.bat test --tests com.example.actuatorguard.ActuatorGuardTest
~~~

12 tests are expected to pass when using the described configuration and environment. The test uses only synthetic data; it does not invoke the branch creating a heapdump or shutting down the JVM.

The tests do not just check HTTP status: they assert that logger levels stay unchanged when denied and cache entries are cleared only when authorized.

Limitations to understand:

- MockMvc uses the test application's Servlet context and does not prove firewalls/proxies in the deployment environment.
- `csrf()` builds valid requests for testing and does not test a real browser's token retrieval flow.
- Being blocked at the heapdump URL does not prove whether the JVM supports dump creation; inventory mappings separately if verifying that capability.
- 403 on `/actuator/beans` proves policy stops the request from proceeding, not that the endpoint was created.
- The logfile test requires file write permissions in the temporary directory; it does not depend on real production logs.

## 8. Separating Management Paths From Public Paths

When taking policies to deployment, check network paths too. Example configuring a separate management port:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

This is a separate deployment example; do not add it to the shared-port test configuration while expecting MockMvc results to stay identical. `management.server.address` can differ from the main server address only when the management port differs from the main port.

`127.0.0.1` is interpreted relative to the process's network namespace. In a container, loopback belongs to that container; it does not mean every component on the host can call it. A proxy, tunnel, or wrong port-publish configuration can still create an unintended access path.

A separate port does not automatically supply TLS, passwords, or authorization. When transmitting credentials over a network, protect the transport; verify TLS configuration on the separate management path instead of inferring from the application port. Related properties are in [HTTP management 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Test from at least two positions:

1. Permitted operational source: connects to the right service and receives the intended authorization policy.
2. Unauthorized source: cannot bypass the network or authentication layer via any other path, including direct domain/IP/port.

If using an identity proxy, never let direct callers supply trusted identity headers themselves. Secure the proxy–backend link and strip untrusted headers at the proper boundary.

Changing base paths or hiding links does not replace these layers. Do not put management endpoints behind a CDN/public cache; do not let downloaded dumps and logs become static assets with public URLs.

## 9. Managing Diagnostic Outputs After Collection

HTTP authorization ends once data is transferred to an authorized caller. Downloaded files also need their own lifecycle:

- Identify the investigator, purpose, and exact data scope truly needed.
- Grant elevated permissions only for the required window; revoke afterward.
- For heapdumps, assess size, disk capacity, load, and JVM impact before collecting.
- Store files where access control and data protection apply; never attach raw dumps to public issues.
- Limit viewers, retention time, and sharing with third parties.
- Log who accessed what, which endpoint, timestamp, and outcome; never log passwords/tokens or sensitive payloads just for auditing.
- After investigation, close temporary exposure/permissions and dispose of copies per retention policy.

For example: opening masked env to find a configuration override source may suffice for an incident. That does not create a reason to download the entire heap. Permissions are chosen to answer the specific question at hand, rather than always granting full diagnostic access.

If you suspect a dump or log containing credentials was leaked, merely closing the URL does not invalidate copies already taken. Assess affected data and rotate/revoke potentially exposed credentials.

## 10. Common Design Mistakes

| Practice | Why it is insufficient |
| --- | --- |
| `include: "*"` and letting every logged-in user access | Regular accounts may receive overly broad diagnostic or control powers |
| Blocking only POST/DELETE | Misses information disclosure risks via GET heapdump/logfile/env |
| Setting only env `show-values: never` | Does not block metadata access and does not sanitize logs/heapdumps |
| Using `when-authorized` without checking role conditions | Can expose raw values to a broader group than intended |
| Granting one permission for reading logs and downloading heaps | Cannot restrict memory investigation privileges separately |
| Checking permissions on the root URL while missing subpaths | May leave env/property or specific cache operations unprotected |
| Allowing everyone to read logfile slices | Slices can still contain sensitive info or be reassembled |
| Disabling CSRF just to make POST succeed | Ignores root cause and authentication assumptions of browser flows |
| Protecting only at the proxy while backend stays directly reachable | Policies can be bypassed via alternative connection paths |
| Disabling HTTP while forgetting an independently enabled JMX channel | Management capabilities may remain over another protocol |
| Testing by taking dumps or running shutdown on live applications | The test itself can leak data or cause disruption |

Not every custom endpoint reveals its side effects in its name. Audit operations, HTTP methods, and execution code of endpoints added by the application or libraries, then place them under a deny-by-default policy before granting intentional permissions.

## 11. Self-Check of Understanding

1. Why can a system allowing only GET still leak critical data through Actuator?
2. Analyst can read masked env but cannot read heapdump: what does this permission boundary protect?
3. Why does changing `show-values` not make a token previously written to logfile disappear?
4. Operator receives 403 on POST logger. How do you distinguish missing permission from a missing CSRF token without disabling checks?
5. Why is testing Range and subpaths more valuable than testing only `/actuator`?
6. When moving from a shared port to a separate management port, which assumptions about context, networking, and TLS must be re-verified?
7. After closing the heapdump endpoint, what risks from an already downloaded file still remain?

A sound policy must answer: **which endpoints truly need to exist, over which channels they appear, who may perform which operations, and how diagnostic data is governed after collection**.
